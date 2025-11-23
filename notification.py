from apprise import Apprise
import config
from datetime import datetime

notifications = []

# FIXME this was existing code (refactored) but do we need to create a new object for each invocation?
def get_apprise():
    apprise = Apprise()

    if config.NOTIFICATION_URLS:
        for url in config.NOTIFICATION_URLS.split(','):
            apprise.add(url.strip())

    return apprise

def batch_message():
    return "\n".join(notifications)

def send_notification(message, title="", error=False, batchable=True):
    """Sends a notification using Apprise.

    Args:
        message (str): The message to send.
        title (str, optional): The title of the notification.
        error (bool, optional): Whether the message is a stack trace. Defaults to False.
        batchable (bool, optional): Whether the message can be batched.
    """
    # Always print to console
    if config.DEBUG:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")
    else:
        print(message)

    apprise = get_apprise()

    if not apprise:
        if config.DEBUG:
            print("[DEBUG] No notification services configured. Check config.NOTIFICATION_URLS.")
        return

    if error:
        message = f"```py\n{message}\n```"

    if config.BATCH_NOTIFICATIONS and batchable:
        notifications.append(message)
    else:
        apprise.notify(body=message, title=title)


def debug_print(message, indent=0):
    """Print debug message with indentation."""
    if config.DEBUG:
        indent_str = "  " * indent
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [DEBUG]{indent_str} {message}")

def send_batch_notification():
    now = datetime.now()
    title = now.strftime(f"Octopus MinMax Results - %a %d %b {config.EXECUTION_TIME if not config.ONE_OFF_RUN else now.strftime('%H:%M:%S')}")
    get_apprise().notify(body=batch_message(), title=title)

    # Clear all notifications
    global notifications
    notifications = []


