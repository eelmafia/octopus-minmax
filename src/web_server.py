from flask import Flask, render_template, request, redirect, flash, Response, jsonify, session
from functools import wraps
import config_manager
import config
import logging
import os
from datetime import datetime
from werkzeug.security import check_password_hash
import ssl
import threading
try:
    import paho.mqtt.client as mqtt
except Exception:  # pragma: no cover - optional dependency at runtime
    mqtt = None

logger = logging.getLogger('octobot.web_server')

app = Flask(__name__)
app.secret_key = 'octobot-tool'
CONFIG_PATH = os.getenv("OCTOBOT_CONFIG_PATH", "/config/config.json")

def _is_password_hash(value):
    if not value:
        return False
    return value.startswith(("pbkdf2:", "scrypt:", "argon2:", "sha256:"))

def is_ingress_request():
    # Skip auth for ingress requests
    return bool(request.headers.get('X-Ingress-Path') or request.headers.get('X-Hassio-Ingress'))

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if is_ingress_request():
            return f(*args, **kwargs)
        if not os.path.exists(CONFIG_PATH):
            return f(*args, **kwargs)
        auth = request.authorization
        if not auth:
            return Response(
                'Authentication required',
                401,
                {'WWW-Authenticate': 'Basic realm="OctoBot Login Required"'}
            )
        if auth.username != config.WEB_USERNAME:
            return Response(
                'Authentication required',
                401,
                {'WWW-Authenticate': 'Basic realm="OctoBot Login Required"'}
            )
        try:
            password_ok = check_password_hash(config.WEB_PASSWORD, auth.password) if _is_password_hash(config.WEB_PASSWORD) else auth.password == config.WEB_PASSWORD
        except ValueError:
            password_ok = False
        if not password_ok:
            return Response(
                'Authentication required',
                401,
                {'WWW-Authenticate': 'Basic realm="OctoBot Login Required"'}
            )
        return f(*args, **kwargs)
    return decorated


@app.route('/')
@require_auth
def index():
    """Homepage - Dashboard with navigation buttons"""
    missing_config = not os.path.exists(CONFIG_PATH)
    current_config = config_manager.get_config()
    tariffs_display = _format_tariffs(current_config.get('tariffs', ''))
    run_prefix = _next_run_prefix(current_config.get('execution_time', ''))
    last_run_summary = _build_last_run_summary(config_manager.load_last_run())
    return render_template('index.html', missing_config=missing_config, config=current_config, tariffs_display=tariffs_display, run_prefix=run_prefix, last_run_summary=last_run_summary)

def _format_tariffs(value):
    items = [item.strip() for item in (value or '').split(',') if item.strip()]
    items = [item[:1].upper() + item[1:] if item else item for item in items]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])} and {items[-1]}"

def _next_run_prefix(value):
    try:
        if not value:
            return "today at"
        run_time = datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return "today at"

    now_time = datetime.now().time()
    return "tomorrow at" if now_time >= run_time else "today at"

def _build_last_run_summary(last_run):
    if not isinstance(last_run, dict):
        return None
    decision = last_run.get('decision')
    if not isinstance(decision, dict):
        return None
    action = decision.get('action')
    reason = decision.get('reason')
    dry_run = bool(decision.get('dry_run'))
    raw_datetime = last_run.get('datetime')
    if not action or not raw_datetime:
        return None

    when_text = raw_datetime
    try:
        parsed = datetime.fromisoformat(raw_datetime.replace('Z', '+00:00'))
        when_text = parsed.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        pass

    reason_map = {
        'already_cheapest': "Already on the cheapest tariff.",
        'dry_run': "Dry run.",
        'threshold_not_met': "Savings below threshold.",
        'error': "Switch failed.",
    }
    action_text = "Switched" if action == "switched" else "Did not switch"
    reason_text = reason_map.get(reason, reason).rstrip(".") if reason else None
    if action == "switched":
        reason_text = None
    if reason == "threshold_not_met":
        savings_pence = decision.get('savings_pence')
        threshold_pence = decision.get('threshold_pence')
        if savings_pence is not None and threshold_pence is not None:
            reason_text = f"Savings (£{savings_pence / 100:.2f}) below threshold (£{threshold_pence / 100:.2f})"
            if dry_run:
                reason_text = f"Dry run - {reason_text}."
    if reason == "already_cheapest" and dry_run:
        reason_text = f"Dry run - {reason_text}."
    if reason == "dry_run":
        savings_pence = decision.get('savings_pence')
        threshold_pence = decision.get('threshold_pence')
        if savings_pence is not None and threshold_pence is not None:
            switch_phrase = "switch skipped" if savings_pence > threshold_pence else "switch would not have been attempted"
            comparator = "above" if savings_pence > threshold_pence else "below"
            reason_text = (
                f"Dry run - {switch_phrase} - "
                f"savings (£{savings_pence / 100:.2f}) were {comparator} threshold (£{threshold_pence / 100:.2f})"
            )

    cheapest_id = decision.get('cheapest_tariff_id')
    tariff_name = None
    if cheapest_id:
        current = last_run.get('currenttariff')
        if isinstance(current, dict) and current.get('id') == cheapest_id:
            tariff_name = current.get('name')
        else:
            for comparison in last_run.get('comparisons', []):
                if comparison.get('id') == cheapest_id:
                    tariff_name = comparison.get('name')
                    break
    tariff_text = tariff_name or "Unknown"

    cost_text = None
    cost_today = decision.get('cost_today')
    if isinstance(cost_today, dict):
        total_pence = cost_today.get('totalcost_pence')
        con_pence = cost_today.get('consumptioncost_pence')
        sc_pence = cost_today.get('standingcharge_pence')
        if total_pence is not None:
            cost_text = f"£{total_pence / 100:.2f}"
            if con_pence is not None and sc_pence is not None:
                cost_text += f" (£{con_pence / 100:.2f} con + £{sc_pence / 100:.2f} s/c)"

    summary = (
        f"<strong>Outcome:</strong> {action_text}. "
        f"<strong>Tariff:</strong> {tariff_text}."
    )
    if reason_text:
        summary = f"{summary} <strong>Rationale:</strong> {reason_text}."

    if action == "switched":
        savings_pence = decision.get('savings_pence')
        if savings_pence is not None:
            summary = f"{summary} <strong>Savings:</strong> £{savings_pence / 100:.2f}."
    if cost_text:
        summary = f"{summary} <strong>Cost today:</strong> {cost_text}."
    else:
        summary = f"{summary}."
    return {
        'title': f"Last run: {when_text}",
        'body': summary,
    }


@app.route('/config', methods=['GET', 'POST'])
@require_auth
def config_page():
    if request.method == 'POST':
        # Validate input
        errors = config_manager.validate_config(
            request.form.to_dict(),
            require_web_auth=not is_ingress_request(),
        )
        if errors:
            first_error = errors[0]
            error_map = _build_error_map(errors)
            field_id, _anchor = _error_to_field_anchor(first_error)
            logger.info("Config validation failed: %s field(s): %s", len(error_map), ", ".join(error_map.keys()))
            current_config = config_manager.get_config()
            missing_config = not os.path.exists(CONFIG_PATH)
            return render_template(
                'config.html',
                config=current_config,
                missing_config=missing_config,
                error_field=field_id,
                error_map=error_map,
                show_flash=False
            )
        else:
            # Update config
            try:
                submitted_values = request.form.to_dict()
                logger.info(f"Config update submitted: {submitted_values}")

                config_manager.update_config(request.form.to_dict())

                new_config = config_manager.get_config()
                logger.info(f"Config updated successfully. New state: {new_config}")

                session['focus_top'] = True
                session['updated'] = True
            except Exception as e:
                flash(f'Error updating config: {str(e)}', 'error')
                logger.error(f"Config update failed: {e}")

        return redirect('config')

    config_manager.load_persisted_config()
    current_config = config_manager.get_config()
    missing_config = not os.path.exists(CONFIG_PATH)
    error_field = ''
    focus_top = session.pop('focus_top', False)
    updated = session.pop('updated', False)
    error_map = {}
    show_flash = not bool(error_field)
    return render_template(
        'config.html',
        config=current_config,
        missing_config=missing_config,
        error_field=error_field,
        focus_top=focus_top,
        error_map=error_map,
        updated=updated,
        show_flash=show_flash
    )


@app.route('/logs')
@require_auth
def logs():
    level = str(session.get('log_level', 'ALL')).upper()
    log_lines = tail_file('logs/octobot.log', None)  # None = read entire file
    log_entries = group_log_entries(log_lines)
    log_entries = _filter_log_entries(log_entries, level)
    return render_template('logs.html', log_entries=log_entries, selected_level=level)

@app.route('/logs/entries', methods=['POST'])
@require_auth
def logs_entries():
    payload = request.get_json(silent=True) or {}
    lines = payload.get('lines', 200)
    level = str(payload.get('level', session.get('log_level', 'ALL'))).upper()
    try:
        line_count = int(lines)
        if line_count <= 0:
            line_count = 200
    except ValueError:
        line_count = 200

    session['log_level'] = level
    session['log_lines'] = line_count
    log_lines = tail_file('logs/octobot.log', line_count)
    log_entries = group_log_entries(log_lines)
    log_entries = _filter_log_entries(log_entries, level)
    return jsonify(log_entries)


@app.route('/mqtt/test', methods=['POST'])
@require_auth
def mqtt_test():
    payload = request.get_json(silent=True) or request.form.to_dict()
    host = (payload or {}).get('mqtt_host') or config.MQTT_HOST
    port_raw = (payload or {}).get('mqtt_port') or config.MQTT_PORT
    username = (payload or {}).get('mqtt_username') or config.MQTT_USERNAME
    password = (payload or {}).get('mqtt_password') or config.MQTT_PASSWORD
    use_tls = str((payload or {}).get('mqtt_use_tls') or config.MQTT_USE_TLS).lower() in ['true', '1', 'yes', 'on']
    tls_insecure = str((payload or {}).get('mqtt_tls_insecure') or config.MQTT_TLS_INSECURE).lower() in ['true', '1', 'yes', 'on']
    ca_cert = (payload or {}).get('mqtt_ca_cert') or config.MQTT_CA_CERT
    client_cert = (payload or {}).get('mqtt_client_cert') or config.MQTT_CLIENT_CERT
    client_key = (payload or {}).get('mqtt_client_key') or config.MQTT_CLIENT_KEY
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        logger.warning("MQTT test failed: invalid port %r", port_raw)
        return jsonify({'ok': False, 'message': 'Invalid port'}), 400
    if not host:
        logger.warning("MQTT test failed: missing host")
        return jsonify({'ok': False, 'message': 'MQTT host is required'}), 400
    if mqtt is None:
        logger.warning("MQTT test failed: paho-mqtt not installed")
        return jsonify({'ok': False, 'message': 'paho-mqtt is not installed'}), 500
    try:
        connect_event = threading.Event()
        result = {'rc': None}

        def _on_connect(client, userdata, flags, rc, properties=None):
            result['rc'] = rc
            connect_event.set()

        def _on_disconnect(client, userdata, rc, properties=None):
            if result['rc'] is None:
                result['rc'] = rc
            connect_event.set()

        client = mqtt.Client()
        if username or password:
            client.username_pw_set(username or None, password or None)
        if use_tls:
            if ca_cert or client_cert or client_key:
                client.tls_set(
                    ca_certs=ca_cert or None,
                    certfile=client_cert or None,
                    keyfile=client_key or None,
                    tls_version=ssl.PROTOCOL_TLS_CLIENT,
                )
            else:
                client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
            if tls_insecure:
                client.tls_insecure_set(True)
        client.on_connect = _on_connect
        client.on_disconnect = _on_disconnect
        client.connect(host, port, keepalive=10)
        client.loop_start()
        connected = connect_event.wait(timeout=5)
        client.disconnect()
        client.loop_stop()
        if not connected:
            logger.warning("MQTT test failed: connection timed out (%s:%s)", host, port)
            return jsonify({'ok': False, 'message': 'Connection timed out'}), 200
        if result['rc'] == 0:
            logger.info("MQTT test succeeded: connected to %s:%s", host, port)
            return jsonify({'ok': True, 'message': f'Connected to {host}:{port}'}), 200
        error_text = mqtt.connack_string(result['rc'])
        logger.warning("MQTT test failed: %s (%s:%s)", error_text, host, port)
        return jsonify({'ok': False, 'message': f'Connection failed: {error_text}'}), 200
    except Exception as exc:
        logger.warning("MQTT test failed: %s (%s:%s)", exc, host, port)
        return jsonify({'ok': False, 'message': f'Connection failed: {exc}'}), 200


def tail_file(filepath, n):
    """Read last n lines from file, or entire file if n is None"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if n is None:
                return lines  # Return entire file
            return lines[-n:] if len(lines) > n else lines
    except FileNotFoundError:
        return ["Log file not found. The bot may not have started yet."]
    except Exception as e:
        logger.error(f"Error reading log file: {e}")
        return [f"Error reading log file: {str(e)}"]


def group_log_entries(log_lines):
    """Group log lines into entries based on timestamp pattern"""
    import re

    # Pattern matches timestamp
    timestamp_pattern = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')

    entries = []
    current_entry = []

    for line in log_lines:
        if timestamp_pattern.match(line):
            # New log entry starts
            if current_entry:
                entries.append(''.join(current_entry))
            current_entry = [line]
        else:
            # Continuation of previous entry
            if current_entry:
                current_entry.append(line)
            else:
                # Edge case: file starts without timestamp
                current_entry.append(line)

    if current_entry:
        entries.append(''.join(current_entry))

    return entries


def _filter_log_entries(log_entries, level):
    if level in ("", "ALL"):
        return log_entries
    filtered = []
    for entry in log_entries:
        entry_level = _extract_log_level(entry)
        if entry_level == level:
            filtered.append(entry)
    return filtered


def _extract_log_level(entry):
    import re
    match = re.search(r' - (DEBUG|INFO|WARNING|ERROR|CRITICAL) - ', entry)
    return match.group(1) if match else None


def run_server():
    logger.info(f"Web server starting on http://localhost:{config.WEB_PORT}")
    app.run(host='0.0.0.0', port=config.WEB_PORT, debug=False, use_reloader=False)


def _error_to_field_anchor(message):
    mapping = {
        "API key is required": ("api_key", "api-settings"),
        "Account number is required": ("acc_number", "api-settings"),
        "Base URL is required": ("base_url", "api-settings"),
        "Execution time is required": ("execution_time", "execution-settings"),
        "Execution time must be in HH:MM format (00:00 to 23:59)": ("execution_time", "execution-settings"),
        "Switch threshold is required": ("switch_threshold", "execution-settings"),
        "Switch threshold must be positive": ("switch_threshold", "execution-settings"),
        "Switch threshold must be a number": ("switch_threshold", "execution-settings"),
        "Tariffs are required": ("tariffs", "tariff-settings"),
        "Notification URLs are required when batch notifications are enabled": ("notification_urls", "notification-settings"),
        "Web username is required": ("web_username", "web-settings"),
        "Web password is required": ("web_password", "web-settings"),
        "MQTT host is required when MQTT is enabled": ("mqtt_host", "mqtt-settings"),
        "MQTT port is required when MQTT is enabled": ("mqtt_port", "mqtt-settings"),
        "MQTT port must be a positive number": ("mqtt_port", "mqtt-settings"),
        "MQTT port must be a number": ("mqtt_port", "mqtt-settings"),
        "MQTT topic is required when MQTT is enabled": ("mqtt_topic", "mqtt-settings"),
    }
    return mapping.get(message, ("", ""))


def _build_error_map(errors):
    error_map = {}
    for error in errors:
        field_id, _anchor = _error_to_field_anchor(error)
        if field_id and field_id not in error_map:
            error_map[field_id] = error
    return error_map
