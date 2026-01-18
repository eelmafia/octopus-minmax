from bot_orchestrator import BotOrchestrator
import logger
import threading
import web_server
import config_manager
import config
app_logger = logger.logger

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
