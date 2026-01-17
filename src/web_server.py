from flask import Flask, render_template, request, redirect, flash, Response, jsonify
from functools import wraps
import config_manager
import config
import logging
import os
from datetime import datetime
from werkzeug.security import check_password_hash

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
        errors = config_manager.validate_config(request.form.to_dict())
        if errors:
            for error in errors:
                flash(error, 'error')
        else:
            # Update config
            try:
                submitted_values = request.form.to_dict()
                logger.info(f"Config update submitted: {submitted_values}")

                config_manager.update_config(request.form.to_dict())

                new_config = config_manager.get_config()
                logger.info(f"Config updated successfully. New state: {new_config}")

                flash('Configuration updated successfully!', 'success')
            except Exception as e:
                flash(f'Error updating config: {str(e)}', 'error')
                logger.error(f"Config update failed: {e}")

        return redirect('config')

    config_manager.load_persisted_config()
    current_config = config_manager.get_config()
    missing_config = not os.path.exists(CONFIG_PATH)
    return render_template('config.html', config=current_config, missing_config=missing_config)


@app.route('/logs')
@require_auth
def logs():
    log_lines = tail_file('logs/octobot.log', None)  # None = read entire file
    log_entries = group_log_entries(log_lines)
    return render_template('logs.html', log_entries=log_entries)

@app.route('/logs/entries')
@require_auth
def logs_entries():
    lines = request.args.get('lines', default='200')
    try:
        line_count = int(lines)
        if line_count <= 0:
            line_count = 200
    except ValueError:
        line_count = 200

    log_lines = tail_file('logs/octobot.log', line_count)
    log_entries = group_log_entries(log_lines)
    return jsonify(log_entries)


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


def run_server():
    logger.info(f"Web server starting on http://localhost:{config.WEB_PORT}")
    app.run(host='0.0.0.0', port=config.WEB_PORT, debug=False, use_reloader=False)
