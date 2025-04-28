import time
from datetime import datetime
import random
import sentry_sdk
import config
from main import run_tariff_compare, send_notification

# Track last execution date to ensure we only run once per day
last_execution_date = None

if config.ONE_OFF_RUN:
    send_notification(message=f"Octobot {config.BOT_VERSION} on. Running a one off comparison.")
    run_tariff_compare()
    # After a one-off run, if Sentry is configured, flush events before exiting
    if config.SENTRY_DSN:
        sentry_sdk.flush()
else:
    # Initialize Sentry if DSN is provided
    if config.SENTRY_DSN:
        sentry_sdk.init(
            dsn=config.SENTRY_DSN,
            release=config.BOT_VERSION,
            traces_sample_rate=1.0,
        )
        sentry_sdk.set_user({"id": config.ACC_NUMBER, "account_number": config.ACC_NUMBER})
        send_notification(message=f"Sentry initialized.")

    send_notification(message=f"Welcome to Octopus MinMax Bot. I will run your comparisons at {config.EXECUTION_TIME}")

    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_date = now.date()

        if current_time == config.EXECUTION_TIME and last_execution_date != current_date:
            last_execution_date = current_date
            # 10 Sec - 10 Min Random Delay to prevent all users attempting to access API at same time
            delay = random.randint(10,600)
            send_notification(message=f"Octobot {config.BOT_VERSION} on. Initiating comparison in {delay/60:.1f} minutes")
            delay = time.sleep(delay)
            run_tariff_compare()

        time.sleep(30) # Check time every 30 seconds

        if config.SENTRY_DSN:
            sentry_sdk.flush()
