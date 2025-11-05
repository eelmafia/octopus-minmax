import os

#  The bot will declare its version in the welcome message.
# Updated by the release pipeline. Change manually if building from source
BOT_VERSION = "v.local"
# Add your stuff here
API_KEY = os.getenv("API_KEY", "")
# Your Octopus Energy account number. Starts with A-
ACC_NUMBER = os.getenv("ACC_NUMBER", "")
BASE_URL = os.getenv("BASE_URL", "https://api.octopus.energy/v1")
# Comma-separated list of Apprise notification URLs
NOTIFICATION_URLS = os.getenv("NOTIFICATION_URLS", "")
# Whether to send all the notifications as a batch or individually
BATCH_NOTIFICATIONS = os.getenv("BATCH_NOTIFICATIONS", "false") in ["true", "True", "1"]

EXECUTION_TIME = os.getenv("EXECUTION_TIME", "23:00")

# A threshold (in pence) over which the difference between the tariffs must be before the switch happens.
SWITCH_THRESHOLD = int(os.getenv("SWITCH_THRESHOLD", 2))

# List of tariff IDs to compare
TARIFFS = os.getenv("TARIFFS", "go,agile,flexible")

# Whether to just run immediately and exit
ONE_OFF_RUN = os.getenv("ONE_OFF", "false") in ["true", "True", "1"]

# Whether to notify the user of a switch but not actually switch
DRY_RUN = os.getenv("DRY_RUN", "false") in ["true", "True", "1"]
