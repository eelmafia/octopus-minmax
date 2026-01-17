import threading
import re
import json
import os
import logging
import config
from werkzeug.security import generate_password_hash

_config_lock = threading.Lock()
_CONFIG_PATH = os.getenv("OCTOBOT_CONFIG_PATH", "/config/config.json")
_LASTRUN_PATH = os.path.join(os.path.dirname(_CONFIG_PATH), "lastrun.json")
logger = logging.getLogger('octobot.config_manager')

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

    if 'API_KEY' in values:
        config.API_KEY = values['API_KEY']
    if 'ACC_NUMBER' in values:
        config.ACC_NUMBER = values['ACC_NUMBER']
    if 'BASE_URL' in values:
        config.BASE_URL = values['BASE_URL']
    if 'EXECUTION_TIME' in values:
        config.EXECUTION_TIME = values['EXECUTION_TIME']
    if 'SWITCH_THRESHOLD' in values:
        try:
            config.SWITCH_THRESHOLD = int(values['SWITCH_THRESHOLD'])
        except (TypeError, ValueError):
            pass
    if 'TARIFFS' in values:
        config.TARIFFS = values['TARIFFS']
    if 'ONE_OFF' in values:
        config.ONE_OFF_RUN = _coerce_bool(values['ONE_OFF'], config.ONE_OFF_RUN)
    if 'DRY_RUN' in values:
        config.DRY_RUN = _coerce_bool(values['DRY_RUN'], config.DRY_RUN)
    if 'NOTIFICATION_URLS' in values:
        config.NOTIFICATION_URLS = values['NOTIFICATION_URLS']
    if 'BATCH_NOTIFICATIONS' in values:
        config.BATCH_NOTIFICATIONS = _coerce_bool(values['BATCH_NOTIFICATIONS'], config.BATCH_NOTIFICATIONS)
    if 'WEB_USERNAME' in values:
        config.WEB_USERNAME = values['WEB_USERNAME']
    if 'WEB_PASSWORD' in values:
        config.WEB_PASSWORD = values['WEB_PASSWORD']

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
        'WEB_USERNAME': config.WEB_USERNAME,
        'WEB_PASSWORD': config.WEB_PASSWORD,
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


def validate_config(config_dict):
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
    if not config_dict.get('web_username'):
        errors.append("Web username is required")

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

    if not os.path.exists(_CONFIG_PATH) or not config.WEB_PASSWORD:
        if not config_dict.get('web_password'):
            errors.append("Web password is required")

    return errors
