from bot_orchestrator import BotOrchestrator
import logger
import threading
import web_server
import config_manager
import config
import os
app_logger = logger.logger

def _is_ingress_environment():
    return bool(os.getenv("SUPERVISOR_TOKEN") or os.getenv("HASSIO_TOKEN") or os.path.exists("/data/options.json"))

config_manager.migrate_options_if_needed()
config_manager.load_persisted_config()
config_manager.warn_if_missing_config()

orchestrator = BotOrchestrator()
bot_thread = threading.Thread(target=orchestrator.start, daemon=False, name="BotThread")
ingress_env = _is_ingress_environment()
if ingress_env and config.NO_WEB_SERVER:
    app_logger.info("Ignoring NO_WEB_SERVER because ingress is enabled.")
no_web_server = config.NO_WEB_SERVER and not ingress_env
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
