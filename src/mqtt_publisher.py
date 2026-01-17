import json
import logging
import re

import config
import paho.mqtt.client as mqtt

logger = logging.getLogger('octobot.mqtt_publisher')

DISCOVERY_PREFIX = "homeassistant"


def _sanitize_device_id(value):
    safe = re.sub(r'[^a-zA-Z0-9_]+', '_', value.strip())
    return safe.lower().strip('_') or "octobot"


def _device_info(device_id):
    return {
        "identifiers": [device_id],
        "name": "Octopus MinMax",
        "model": "Octopus MinMax Bot",
        "manufacturer": "Octopus Energy",
    }


def _publish(client, topic, payload, retain=True):
    client.publish(topic, payload, qos=0, retain=retain)


def _publish_sensor_config(client, device_id, object_id, name, state_topic, value_template, unit=None, icon=None):
    config_payload = {
        "name": name,
        "object_id": f"octopus_minmax_{object_id}",
        "state_topic": state_topic,
        "unique_id": f"{device_id}_{object_id}",
        "value_template": value_template,
        "device": _device_info(device_id),
    }
    if unit:
        config_payload["unit_of_measurement"] = unit
    if icon:
        config_payload["icon"] = icon

    config_topic = f"{DISCOVERY_PREFIX}/sensor/{device_id}/{object_id}/config"
    _publish(client, config_topic, json.dumps(config_payload), retain=True)


def _build_state_payload(payload):
    decision = payload.get("decision", {}) if isinstance(payload, dict) else {}
    action = decision.get("action")
    reason = decision.get("reason") or ""
    cheapest_id = decision.get("cheapest_tariff_id")

    tariff_name = None
    current = payload.get("currenttariff", {}) if isinstance(payload, dict) else {}
    if isinstance(current, dict) and current.get("id") == cheapest_id:
        tariff_name = current.get("name")
    else:
        for comparison in payload.get("comparisons", []) if isinstance(payload, dict) else []:
            if comparison.get("id") == cheapest_id:
                tariff_name = comparison.get("name")
                break
    if tariff_name is None:
        tariff_name = current.get("name") if isinstance(current, dict) else ""

    cost_today = decision.get("cost_today") if isinstance(decision, dict) else {}
    cost_today = cost_today if isinstance(cost_today, dict) else {}

    return {
        "action": action,
        "reason": reason,
        "dry_run": bool(decision.get("dry_run")),
        "tariff_name": tariff_name or "",
        "savings_pence": decision.get("savings_pence"),
        "threshold_pence": decision.get("threshold_pence"),
        "cost_today_total_pence": cost_today.get("totalcost_pence"),
        "cost_today_consumption_pence": cost_today.get("consumptioncost_pence"),
        "cost_today_standingcharge_pence": cost_today.get("standingcharge_pence"),
        "totalconsumption_kwh": payload.get("totalconsumption_kwh") if isinstance(payload, dict) else None,
        "datetime": payload.get("datetime") if isinstance(payload, dict) else None,
        "raw": payload,
    }


def publish_results(payload):
    if not config.MQTT_ENABLED:
        return False
    if not config.MQTT_HOST or not config.MQTT_TOPIC:
        logger.warning("MQTT publish skipped: host or topic missing.")
        return False

    device_id = _sanitize_device_id(config.ACC_NUMBER or "octobot")
    state_topic = f"{config.MQTT_TOPIC}/state"
    state_payload = _build_state_payload(payload)

    client = mqtt.Client()
    if config.MQTT_USERNAME or config.MQTT_PASSWORD:
        client.username_pw_set(config.MQTT_USERNAME or None, config.MQTT_PASSWORD or None)

    try:
        client.connect(config.MQTT_HOST, config.MQTT_PORT, keepalive=10)
        client.loop_start()

        _publish_sensor_config(
            client, device_id, "action", "Outcome", state_topic, "{{ value_json.action }}", icon="mdi:swap-horizontal"
        )
        _publish_sensor_config(
            client, device_id, "reason", "Rationale", state_topic, "{{ value_json.reason }}", icon="mdi:information-outline"
        )
        _publish_sensor_config(
            client, device_id, "tariff", "Tariff", state_topic, "{{ value_json.tariff_name }}", icon="mdi:information-outline"
        )
        _publish_sensor_config(
            client, device_id, "savings", "Savings", state_topic, "{{ value_json.savings_pence }}", unit="p", icon="mdi:currency-gbp"
        )
        _publish_sensor_config(
            client, device_id, "threshold", "Threshold", state_topic, "{{ value_json.threshold_pence }}", unit="p", icon="mdi:currency-gbp"
        )
        _publish_sensor_config(
            client, device_id, "cost_today", "Cost Today", state_topic, "{{ value_json.cost_today_total_pence }}", unit="p", icon="mdi:currency-gbp"
        )
        _publish_sensor_config(
            client, device_id, "consumption_cost", "Consumption Cost", state_topic, "{{ value_json.cost_today_consumption_pence }}", unit="p", icon="mdi:currency-gbp"
        )
        _publish_sensor_config(
            client, device_id, "standing_charge", "Standing Charge", state_topic, "{{ value_json.cost_today_standingcharge_pence }}", unit="p", icon="mdi:currency-gbp"
        )
        _publish_sensor_config(
            client, device_id, "totalconsumption_kwh", "Total Consumption", state_topic, "{{ value_json.totalconsumption_kwh }}", unit="kWh", icon="mdi:counter"
        )
        _publish_sensor_config(
            client, device_id, "datetime", "Last Run", state_topic, "{{ value_json.datetime }}", icon="mdi:clock-outline"
        )
        _publish_sensor_config(
            client, device_id, "dry_run", "Dry Run", state_topic, "{{ value_json.dry_run }}", icon="mdi:information-outline"
        )

        _publish(client, state_topic, json.dumps(state_payload), retain=True)
        return True
    except Exception as exc:
        logger.warning("MQTT publish failed: %s", exc)
        return False
    finally:
        try:
            client.disconnect()
            client.loop_stop()
        except Exception:
            pass
