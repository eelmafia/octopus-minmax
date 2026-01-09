from bot_orchestrator import BotOrchestrator
import logger
import threading
import web_server

orchestrator = BotOrchestrator()
bot_thread = threading.Thread(target=orchestrator.start, daemon=False, name="BotThread")
web_thread = threading.Thread(target=web_server.run_server, daemon=False, name="WebThread")

# Start both threads
print("Starting bot thread...")
bot_thread.start()

print("Starting web server thread...")
web_thread.start()
bot_thread.join()
web_thread.join()