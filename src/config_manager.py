import threading
import re
import json
import os
import logging
import config
import secrets
from werkzeug.security import generate_password_hash

_config_lock = threading.Lock()
_CONFIG_PATH = os.getenv("OCTOBOT_CONFIG_PATH", "/config/config.json")
_LASTRUN_PATH = os.path.join(os.path.dirname(_CONFIG_PATH), "lastrun.json")
logger = logging.getLogger('octobot.config_manager')
_ENV_CONFIG_KEYS = [
    "API_KEY",
    "ACC_NUMBER",
    "BASE_URL",
    "EXECUTION_TIME",
    "SWITCH_THRESHOLD",
    "TARIFFS",
    "ONE_OFF",
    "DRY_RUN",
    "NOTIFICATION_URLS",
    "BATCH_NOTIFICATIONS",
    "ONLY_RESULTS_NOTIFICATIONS",
    "MQTT_ENABLED",
    "MQTT_HOST",
    "MQTT_PORT",
    "MQTT_USERNAME",
    "MQTT_PASSWORD",
    "MQTT_TOPIC",
    "MQTT_USE_TLS",
    "MQTT_TLS_INSECURE",
    "MQTT_CA_CERT",
    "MQTT_CLIENT_CERT",
    "MQTT_CLIENT_KEY",
    "WEB_USERNAME",
    "WEB_PASSWORD",
    "WEB_PORT",
    "NO_WEB_SERVER",
]

def _env_overrides(key):
    return os.getenv(key) not in (None, "")

def _has_env_overrides():
    return any(_env_overrides(key) for key in _ENV_CONFIG_KEYS)

def _coerce_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ['true', '1', 'yes', 'on']
    if isinstance(value, (int, float)):
        return value != 0
    return default

def _apply_persisted_values(values):
    if not isinstance(values, dict):
        return

    if 'API_KEY' in values and not _env_overrides('API_KEY'):
        config.API_KEY = values['API_KEY']
    if 'ACC_NUMBER' in values and not _env_overrides('ACC_NUMBER'):
        config.ACC_NUMBER = values['ACC_NUMBER']
    if 'BASE_URL' in values and not _env_overrides('BASE_URL'):
        config.BASE_URL = values['BASE_URL']
    if 'EXECUTION_TIME' in values and not _env_overrides('EXECUTION_TIME'):
        config.EXECUTION_TIME = values['EXECUTION_TIME']
    if 'SWITCH_THRESHOLD' in values and not _env_overrides('SWITCH_THRESHOLD'):
        try:
            config.SWITCH_THRESHOLD = int(values['SWITCH_THRESHOLD'])
        except (TypeError, ValueError):
            pass
    if 'TARIFFS' in values and not _env_overrides('TARIFFS'):
        config.TARIFFS = values['TARIFFS']
    if 'ONE_OFF' in values and not _env_overrides('ONE_OFF'):
        config.ONE_OFF_RUN = _coerce_bool(values['ONE_OFF'], config.ONE_OFF_RUN)
    if 'DRY_RUN' in values and not _env_overrides('DRY_RUN'):
        config.DRY_RUN = _coerce_bool(values['DRY_RUN'], config.DRY_RUN)
    if 'NOTIFICATION_URLS' in values and not _env_overrides('NOTIFICATION_URLS'):
        config.NOTIFICATION_URLS = values['NOTIFICATION_URLS']
    if 'BATCH_NOTIFICATIONS' in values and not _env_overrides('BATCH_NOTIFICATIONS'):
        config.BATCH_NOTIFICATIONS = _coerce_bool(values['BATCH_NOTIFICATIONS'], config.BATCH_NOTIFICATIONS)
    if 'ONLY_RESULTS_NOTIFICATIONS' in values and not _env_overrides('ONLY_RESULTS_NOTIFICATIONS'):
        config.ONLY_RESULTS_NOTIFICATIONS = _coerce_bool(values['ONLY_RESULTS_NOTIFICATIONS'], config.ONLY_RESULTS_NOTIFICATIONS)
    if 'MQTT_ENABLED' in values and not _env_overrides('MQTT_ENABLED'):
        config.MQTT_ENABLED = _coerce_bool(values['MQTT_ENABLED'], config.MQTT_ENABLED)
    if 'MQTT_HOST' in values and not _env_overrides('MQTT_HOST'):
        config.MQTT_HOST = values['MQTT_HOST']
    if 'MQTT_PORT' in values and not _env_overrides('MQTT_PORT'):
        try:
            config.MQTT_PORT = int(values['MQTT_PORT'])
        except (TypeError, ValueError):
            pass
    if 'MQTT_USERNAME' in values and not _env_overrides('MQTT_USERNAME'):
        config.MQTT_USERNAME = values['MQTT_USERNAME']
    if 'MQTT_PASSWORD' in values and not _env_overrides('MQTT_PASSWORD'):
        config.MQTT_PASSWORD = values['MQTT_PASSWORD']
    if 'MQTT_TOPIC' in values and not _env_overrides('MQTT_TOPIC'):
        config.MQTT_TOPIC = values['MQTT_TOPIC']
    if 'MQTT_USE_TLS' in values and not _env_overrides('MQTT_USE_TLS'):
        config.MQTT_USE_TLS = _coerce_bool(values['MQTT_USE_TLS'], config.MQTT_USE_TLS)
    if 'MQTT_TLS_INSECURE' in values and not _env_overrides('MQTT_TLS_INSECURE'):
        config.MQTT_TLS_INSECURE = _coerce_bool(values['MQTT_TLS_INSECURE'], config.MQTT_TLS_INSECURE)
    if 'MQTT_CA_CERT' in values and not _env_overrides('MQTT_CA_CERT'):
        config.MQTT_CA_CERT = values['MQTT_CA_CERT']
    if 'MQTT_CLIENT_CERT' in values and not _env_overrides('MQTT_CLIENT_CERT'):
        config.MQTT_CLIENT_CERT = values['MQTT_CLIENT_CERT']
    if 'MQTT_CLIENT_KEY' in values and not _env_overrides('MQTT_CLIENT_KEY'):
        config.MQTT_CLIENT_KEY = values['MQTT_CLIENT_KEY']
    if 'WEB_USERNAME' in values and not _env_overrides('WEB_USERNAME'):
        config.WEB_USERNAME = values['WEB_USERNAME']
    if 'WEB_PASSWORD' in values and not _env_overrides('WEB_PASSWORD'):
        config.WEB_PASSWORD = values['WEB_PASSWORD']
    if 'NO_WEB_SERVER' in values and not _env_overrides('NO_WEB_SERVER'):
        config.NO_WEB_SERVER = _coerce_bool(values['NO_WEB_SERVER'], config.NO_WEB_SERVER)

def load_persisted_config():
    """Load persisted config from /data (Home Assistant) if present."""
    with _config_lock:
        for path in [_CONFIG_PATH]:
            if not os.path.exists(path):
                continue
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    values = json.load(f)
                _apply_persisted_values(values)
                logger.info("Loaded persisted config from %s", path)
                return
            except Exception as exc:
                logger.warning("Failed to load persisted config from %s: %s", path, exc)
        if _has_env_overrides():
            temp_password = secrets.token_urlsafe(12)
            config.WEB_USERNAME = "admin"
            config.WEB_PASSWORD = generate_password_hash(temp_password)
            _persist_config()
            logger.info("Temporary admin password: %s", temp_password)

def warn_if_missing_config():
    if not os.path.exists(_CONFIG_PATH):
        logger.warning("Config file missing at %s. Update configuration to create it.", _CONFIG_PATH)

def get_config():
    """Get current configuration as dictionary (thread-safe)"""
    with _config_lock:
        return {
            'api_key': config.API_KEY,
            'acc_number': config.ACC_NUMBER,
            'base_url': config.BASE_URL,
            'execution_time': config.EXECUTION_TIME,
            'switch_threshold': config.SWITCH_THRESHOLD,
            'tariffs': config.TARIFFS,
            'one_off_run': config.ONE_OFF_RUN,
            'one_off_executed': config.ONE_OFF_EXECUTED,
            'dry_run': config.DRY_RUN,
            'notification_urls': config.NOTIFICATION_URLS,
            'batch_notifications': config.BATCH_NOTIFICATIONS,
            'only_results_notifications': config.ONLY_RESULTS_NOTIFICATIONS,
            'mqtt_enabled': config.MQTT_ENABLED,
            'mqtt_host': config.MQTT_HOST,
            'mqtt_port': config.MQTT_PORT,
            'mqtt_username': config.MQTT_USERNAME,
            'mqtt_password': config.MQTT_PASSWORD,
            'mqtt_topic': config.MQTT_TOPIC,
            'mqtt_use_tls': config.MQTT_USE_TLS,
            'mqtt_tls_insecure': config.MQTT_TLS_INSECURE,
            'mqtt_ca_cert': config.MQTT_CA_CERT,
            'mqtt_client_cert': config.MQTT_CLIENT_CERT,
            'mqtt_client_key': config.MQTT_CLIENT_KEY,
            'web_username': config.WEB_USERNAME,
            'web_password': "",
        }


def update_config(new_values):
    """Update configuration at runtime (called by web UI) - thread-safe"""
    with _config_lock:
        previous_one_off = config.ONE_OFF_RUN

        if 'api_key' in new_values and new_values['api_key']:
            config.API_KEY = new_values['api_key']
        if 'acc_number' in new_values and new_values['acc_number']:
            config.ACC_NUMBER = new_values['acc_number']
        if 'base_url' in new_values and new_values['base_url']:
            config.BASE_URL = new_values['base_url']
        if 'execution_time' in new_values:
            config.EXECUTION_TIME = new_values['execution_time']
        if 'switch_threshold' in new_values:
            config.SWITCH_THRESHOLD = int(new_values['switch_threshold'])
        if 'tariffs' in new_values:
            config.TARIFFS = new_values['tariffs']
        if 'one_off_run' in new_values:
            config.ONE_OFF_RUN = str(new_values['one_off_run']).lower() in ['true', '1', 'yes', 'on']
        else:
            config.ONE_OFF_RUN = False
        if 'dry_run' in new_values:
            config.DRY_RUN = str(new_values['dry_run']).lower() in ['true', '1', 'yes', 'on']
        else:
            # Checkbox not checked means False
            config.DRY_RUN = False
        if 'notification_urls' in new_values:
            config.NOTIFICATION_URLS = new_values['notification_urls']
        if 'batch_notifications' in new_values:
            config.BATCH_NOTIFICATIONS = str(new_values['batch_notifications']).lower() in ['true', '1', 'yes', 'on']
        else:
            # Checkbox not checked means False
            config.BATCH_NOTIFICATIONS = False
        if 'only_results_notifications' in new_values:
            config.ONLY_RESULTS_NOTIFICATIONS = str(new_values['only_results_notifications']).lower() in ['true', '1', 'yes', 'on']
        else:
            config.ONLY_RESULTS_NOTIFICATIONS = False
        if 'mqtt_enabled' in new_values:
            config.MQTT_ENABLED = str(new_values['mqtt_enabled']).lower() in ['true', '1', 'yes', 'on']
        else:
            config.MQTT_ENABLED = False
        if 'mqtt_host' in new_values:
            config.MQTT_HOST = new_values['mqtt_host']
        if 'mqtt_port' in new_values and new_values['mqtt_port']:
            config.MQTT_PORT = int(new_values['mqtt_port'])
        if 'mqtt_username' in new_values:
            config.MQTT_USERNAME = new_values['mqtt_username']
        if 'mqtt_password' in new_values:
            config.MQTT_PASSWORD = new_values['mqtt_password']
        if 'mqtt_topic' in new_values:
            config.MQTT_TOPIC = new_values['mqtt_topic']
        if 'mqtt_use_tls' in new_values:
            config.MQTT_USE_TLS = str(new_values['mqtt_use_tls']).lower() in ['true', '1', 'yes', 'on']
        else:
            config.MQTT_USE_TLS = False
        if 'mqtt_tls_insecure' in new_values:
            config.MQTT_TLS_INSECURE = str(new_values['mqtt_tls_insecure']).lower() in ['true', '1', 'yes', 'on']
        else:
            config.MQTT_TLS_INSECURE = False
        if 'mqtt_ca_cert' in new_values:
            config.MQTT_CA_CERT = new_values['mqtt_ca_cert']
        if 'mqtt_client_cert' in new_values:
            config.MQTT_CLIENT_CERT = new_values['mqtt_client_cert']
        if 'mqtt_client_key' in new_values:
            config.MQTT_CLIENT_KEY = new_values['mqtt_client_key']
        if 'web_username' in new_values and new_values['web_username']:
            config.WEB_USERNAME = new_values['web_username']
        if 'web_password' in new_values and new_values['web_password']:
            config.WEB_PASSWORD = generate_password_hash(new_values['web_password'])

        if config.ONE_OFF_RUN and not previous_one_off:
            config.ONE_OFF_EXECUTED = False

        _persist_config()

def _persist_config():
    payload = {
        'API_KEY': config.API_KEY,
        'ACC_NUMBER': config.ACC_NUMBER,
        'BASE_URL': config.BASE_URL,
        'EXECUTION_TIME': config.EXECUTION_TIME,
        'SWITCH_THRESHOLD': config.SWITCH_THRESHOLD,
        'TARIFFS': config.TARIFFS,
        'ONE_OFF': config.ONE_OFF_RUN,
        'DRY_RUN': config.DRY_RUN,
        'NOTIFICATION_URLS': config.NOTIFICATION_URLS,
        'BATCH_NOTIFICATIONS': config.BATCH_NOTIFICATIONS,
        'ONLY_RESULTS_NOTIFICATIONS': config.ONLY_RESULTS_NOTIFICATIONS,
        'MQTT_ENABLED': config.MQTT_ENABLED,
        'MQTT_HOST': config.MQTT_HOST,
        'MQTT_PORT': config.MQTT_PORT,
        'MQTT_USERNAME': config.MQTT_USERNAME,
        'MQTT_PASSWORD': config.MQTT_PASSWORD,
        'MQTT_TOPIC': config.MQTT_TOPIC,
        'MQTT_USE_TLS': config.MQTT_USE_TLS,
        'MQTT_TLS_INSECURE': config.MQTT_TLS_INSECURE,
        'MQTT_CA_CERT': config.MQTT_CA_CERT,
        'MQTT_CLIENT_CERT': config.MQTT_CLIENT_CERT,
        'MQTT_CLIENT_KEY': config.MQTT_CLIENT_KEY,
        'WEB_USERNAME': config.WEB_USERNAME,
        'WEB_PASSWORD': config.WEB_PASSWORD,
        'NO_WEB_SERVER': config.NO_WEB_SERVER,
    }
    try:
        os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
        with open(_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        logger.info("Persisted config to %s", _CONFIG_PATH)
    except Exception as exc:
        logger.warning("Failed to persist config to %s: %s", _CONFIG_PATH, exc)


def reset_one_off_run():
    with _config_lock:
        config.ONE_OFF_RUN = False
        config.ONE_OFF_EXECUTED = True
        _persist_config()


def persist_last_run(payload):
    if not isinstance(payload, dict):
        return
    with _config_lock:
        try:
            os.makedirs(os.path.dirname(_LASTRUN_PATH), exist_ok=True)
            with open(_LASTRUN_PATH, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2, sort_keys=True)
            logger.info("Persisted last run to %s", _LASTRUN_PATH)
        except Exception as exc:
            logger.warning("Failed to persist last run to %s: %s", _LASTRUN_PATH, exc)


def load_last_run():
    with _config_lock:
        if not os.path.exists(_LASTRUN_PATH):
            return None
        try:
            with open(_LASTRUN_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Failed to load last run from %s: %s", _LASTRUN_PATH, exc)
            return None


def validate_config(config_dict, require_web_auth=True):
    """Validate config values before saving"""
    errors = []

    if not config_dict.get('api_key'):
        errors.append("API key is required")
    if not config_dict.get('acc_number'):
        errors.append("Account number is required")
    if not config_dict.get('base_url'):
        errors.append("Base URL is required")
    if not config_dict.get('execution_time'):
        errors.append("Execution time is required")
    if not config_dict.get('switch_threshold'):
        errors.append("Switch threshold is required")
    if not config_dict.get('tariffs'):
        errors.append("Tariffs are required")
    if require_web_auth:
        if not config_dict.get('web_username'):
            errors.append("Web username is required")

    mqtt_enabled = str(config_dict.get('mqtt_enabled', '')).lower() in ['true', '1', 'yes', 'on']
    if mqtt_enabled:
        if not config_dict.get('mqtt_host'):
            errors.append("MQTT host is required when MQTT is enabled")
        if not config_dict.get('mqtt_port'):
            errors.append("MQTT port is required when MQTT is enabled")
        else:
            try:
                val = int(config_dict['mqtt_port'])
                if val <= 0:
                    errors.append("MQTT port must be a positive number")
            except ValueError:
                errors.append("MQTT port must be a number")
        if not config_dict.get('mqtt_topic'):
            errors.append("MQTT topic is required when MQTT is enabled")

    # Validate execution_time format (HH:MM)
    if 'execution_time' in config_dict:
        if not re.match(r'^([0-1][0-9]|2[0-3]):[0-5][0-9]$', config_dict['execution_time']):
            errors.append("Execution time must be in HH:MM format (00:00 to 23:59)")

    # Validate switch_threshold is positive integer
    if 'switch_threshold' in config_dict:
        try:
            val = int(config_dict['switch_threshold'])
            if val < 0:
                errors.append("Switch threshold must be positive")
        except ValueError:
            errors.append("Switch threshold must be a number")

    batch_notifications = str(config_dict.get('batch_notifications', '')).lower() in ['true', '1', 'yes', 'on']
    if batch_notifications and not config_dict.get('notification_urls'):
        errors.append("Notification URLs are required when batch notifications are enabled")

    if require_web_auth:
        if not os.path.exists(_CONFIG_PATH) or not config.WEB_PASSWORD:
            if not config_dict.get('web_password'):
                errors.append("Web password is required")

    return errors
