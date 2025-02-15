import os

# Add your stuff here
API_KEY = os.getenv("API_KEY", "")
# Your Octopus Energy account number. Starts with A-
ACC_NUMBER = os.getenv("ACC_NUMBER", "")
BASE_URL = os.getenv("BASE_URL", "https://api.octopus.energy/v1")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
OCTOPUS_LOGIN_EMAIL = os.getenv("OCTOPUS_LOGIN_EMAIL", "")
OCTOPUS_LOGIN_PASSWD = os.getenv("OCTOPUS_LOGIN_PASSWD", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
EXECUTION_TIME = os.getenv("EXECUTION_TIME", "23:00")

# Whether to just run immediately and exit
ONE_OFF_RUN = os.getenv("ONE_OFF", "false") in ["true", "True", "1"]

# Whether to notify the user of a switch but not actually switch
DRY_RUN = os.getenv("DRY_RUN", "false") in ["true", "True", "1"]
