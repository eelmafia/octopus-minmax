from bot_orchestrator import BotOrchestrator
import logger
import threading
import web_server
import config_manager
import config
import logging
import os

app_logger = logger.logger
console_handler = next(
    (handler for handler in app_logger.handlers if type(handler) is logging.StreamHandler),
    None,
)
if console_handler:
    original_level = console_handler.level
    console_handler.setLevel(logging.DEBUG)
project_env_keys = {
    "API_KEY",
    "ACC_NUMBER",
    "BASE_URL",
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
    "EXECUTION_TIME",
    "SWITCH_THRESHOLD",
    "TARIFFS",
    "ONE_OFF",
    "DRY_RUN",
    "WEB_USERNAME",
    "WEB_PASSWORD",
    "WEB_PORT",
    "NO_WEB_SERVER",
    "OCTOBOT_CONFIG_PATH",
}
env_snapshot = {key: os.environ[key] for key in project_env_keys if key in os.environ}
app_logger.debug("Project environment variables at startup: %s", env_snapshot)
if console_handler:
    console_handler.setLevel(original_level)

config_manager.load_persisted_config()
config_manager.warn_if_missing_config()

orchestrator = BotOrchestrator()
bot_thread = threading.Thread(target=orchestrator.start, daemon=False, name="BotThread")
no_web_server = config.NO_WEB_SERVER
web_thread = None
if not no_web_server:
    web_thread = threading.Thread(target=web_server.run_server, daemon=False, name="WebThread")
else:
    app_logger.info("Web server disabled via environment variable or config key NO_WEB_SERVER")

# Start both threads
print("Starting bot thread...")
bot_thread.start()

if web_thread:
    print("Starting web server thread...")
    web_thread.start()
bot_thread.join()
if web_thread:
    web_thread.join()
