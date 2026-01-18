import os
import sys

def _apply_cli_config_path():
    if os.getenv("OCTOBOT_CONFIG_PATH"):
        return
    for arg in sys.argv[1:]:
        if arg.startswith("OCTOBOT_CONFIG_PATH="):
            os.environ["OCTOBOT_CONFIG_PATH"] = arg.split("=", 1)[1]
            return

_apply_cli_config_path()

def _has_cli_env_args():
    for arg in sys.argv[1:]:
        if "=" not in arg:
            continue
        key, _value = arg.split("=", 1)
        if key and key != "OCTOBOT_CONFIG_PATH":
            return True
    return False

from bot_orchestrator import BotOrchestrator
import logger
import threading
import web_server
import config_manager
import config
app_logger = logger.logger

def _is_ingress_environment():
    return bool(os.getenv("SUPERVISOR_TOKEN") or os.getenv("HASSIO_TOKEN") or os.path.exists("/data/options.json"))

def _is_docker_runtime():
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", "r", encoding="utf-8") as f:
            data = f.read()
        return "docker" in data or "containerd" in data
    except OSError:
        return False

def _detect_launch_context(ingress_env, docker_env):
    if ingress_env:
        return "Home Assistant Addon"
    if docker_env:
        return "Docker"
    return "Command Line"

ingress_env = _is_ingress_environment()
docker_env = _is_docker_runtime()
app_logger.debug("Launch context: %s", _detect_launch_context(ingress_env, docker_env))

if ingress_env:
    config_manager.migrate_options_if_needed()
elif docker_env:
    config_manager.migrate_env_if_needed()
config_manager.load_persisted_config()
config_manager.warn_if_missing_config()
command_line_mode = not ingress_env and not docker_env
config_path = os.getenv("OCTOBOT_CONFIG_PATH", "/config/config.json")
show_cli_env_notice = (
    command_line_mode
    and not os.path.exists(config_path)
    and (config_manager.has_env_config() or _has_cli_env_args())
)
if show_cli_env_notice:
    app_logger.info(
        "Using environment variables. Config file is not used until the app is launched without environment variables."
    )

orchestrator = BotOrchestrator()
bot_thread = threading.Thread(target=orchestrator.start, daemon=False, name="BotThread")
if ingress_env and config.NO_WEB_SERVER:
    app_logger.debug("Ignoring NO_WEB_SERVER because ingress is enabled.")
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
