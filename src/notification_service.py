from apprise import Apprise
from datetime import datetime
from typing import List, Optional
import logging

import config

logger = logging.getLogger('octobot.notification_service')
DISCORD_CHAR_LIMIT = 1900 # Technically it's 2000 but the "title" and backticks are part of it so this is safer in case the formatting changes

class NotificationService:

    def __init__(self, notification_urls: str, batch_enabled: bool):
        self.notification_urls = notification_urls
        self.batch_notifications: List[str] = []
        self.batch_enabled = batch_enabled
        self._apprise: Optional[Apprise] = None

    def _refresh_from_config(self) -> None:
        if self.notification_urls != config.NOTIFICATION_URLS:
            self.notification_urls = config.NOTIFICATION_URLS
            self._apprise = None
        if self.batch_enabled != config.BATCH_NOTIFICATIONS:
            self.batch_enabled = config.BATCH_NOTIFICATIONS


    def _get_apprise(self) -> Optional[Apprise]:
        if self._apprise is None:
            self._apprise = Apprise()
            for url in self.notification_urls.split(','):
                self._apprise.add(url.strip())

        return self._apprise

    def send_notification(self, message:str, title: str = "", is_error: bool = False, batchable: bool = True) -> bool:
        """Sends a notification using Apprise.

        Args:
            message (str): The message to send.
            title (str, optional): The title of the notification.
            is_error (bool, optional): Whether the message is a stack trace. Defaults to False.
            batchable (bool, optional): Whether the message can be batched.
        """
        self._refresh_from_config()
        apprise = self._get_apprise()

        if is_error:
            # Apprise fails if we try to send a discord message over 2k chars (long stacktraces) so chunk it and send it recursively.
            # I don't like this approach very much but it's the best I could come up with.
            if len(message) > DISCORD_CHAR_LIMIT:
                self.send_notification(message[:-DISCORD_CHAR_LIMIT], "", is_error, batchable)
                message = message[-DISCORD_CHAR_LIMIT:]

            message = f"```py\n{message}\n```"

        if self.batch_enabled and batchable:
            self.batch_notifications.append(message)
            logger.debug(f"Added message to batch. Current batch size: {len(self.batch_notifications)}")
            return True
        else:
            if not apprise:
                logger.warning("No notification services configured. Check config.NOTIFICATION_URLS.")
                logger.info(message)
                return False
            success = apprise.notify(body=message, title=title)
            logger.info(f"Successfuly sent notification: {message}")
            if not success:
                logger.error(f"Failed to send notification: {title}")
            return success

    def send_batch_notification(self) -> bool:
        self._refresh_from_config()
        if not self.batch_notifications:
            logger.debug("No notifications in batch to send")
            return True

        apprise = self._get_apprise()

        now = datetime.now()
        title = now.strftime(f"Octopus MinMax Results - %a %d %b {config.EXECUTION_TIME if not config.ONE_OFF_RUN else now.strftime('%H:%M:%S')}")
        body = "\n".join(self.batch_notifications)

        if not apprise:
            logger.warning("Cannot send batch - no notification services configured. Check config.NOTIFICATION_URLS.")
            logger.info(body)
            return False
        success = apprise.notify(body=body, title=title)
        if success:
            logger.info(f"Sent batch notification with {len(self.batch_notifications)} messages")
            self.batch_notifications.clear()
        else:
            logger.error("Failed to send batch notification")

        return success
