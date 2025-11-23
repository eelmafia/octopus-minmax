import time
from datetime import datetime, timedelta
import random
import config
from main import run_tariff_compare, make_predictive_decision, execute_predictive_switch
from notification import send_notification

# Track last execution date to ensure we only run once per day
last_execution_date = None
last_decision_date = None
last_switch_date = None
decision_retry_scheduled = False

if config.ONE_OFF_RUN:
    send_notification(message=f"Octobot {config.BOT_VERSION} on. Running a one off comparison.")
    if config.PREDICTIVE_MODE:
        from main import query_service, load_tariffs_from_ids
        from query_service import QueryService
        query_service = QueryService(config.API_KEY, config.BASE_URL)
        load_tariffs_from_ids(config.TARIFFS)
        make_predictive_decision()
    else:
        run_tariff_compare()
else:
    if config.PREDICTIVE_MODE:
        send_notification(
            message=f"Welcome to Octobot {config.BOT_VERSION} (Predictive Mode). "
                   f"I will check tomorrow's rates at {config.DECISION_TIME} and switch at {config.SWITCH_TIME}",
            batchable=False
        )
    else:
        send_notification(
            message=f"Welcome to Octobot {config.BOT_VERSION}. I will run your comparisons at {config.EXECUTION_TIME}",
            batchable=False
        )

    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_date = now.date()

        if config.PREDICTIVE_MODE:
            # Predictive mode: Two-phase execution
            # Phase 1: Decision phase at DECISION_TIME
            if current_time == config.DECISION_TIME and last_decision_date != current_date:
                last_decision_date = current_date
                decision_retry_scheduled = False
                
                send_notification(f"Predictive mode: Making decision for tomorrow at {config.DECISION_TIME}...")
                success = make_predictive_decision()
                
                if not success:
                    # Check if we should retry (if before 23:00)
                    if now.hour < 23:
                        decision_retry_scheduled = True
                        send_notification("Will retry decision in 1 hour...")
            
            # Retry decision if scheduled and 1 hour has passed
            elif decision_retry_scheduled and last_decision_date == current_date:
                # Check if an hour has passed since decision time
                decision_time_obj = datetime.strptime(config.DECISION_TIME, "%H:%M").time()
                decision_datetime = datetime.combine(current_date, decision_time_obj)
                if now >= decision_datetime + timedelta(hours=1):
                    decision_retry_scheduled = False
                    send_notification("Retrying decision for tomorrow...")
                    make_predictive_decision()
            
            # Phase 2: Switch phase at SWITCH_TIME
            if current_time == config.SWITCH_TIME and last_switch_date != current_date:
                last_switch_date = current_date
                
                send_notification(f"Predictive mode: Executing switch at {config.SWITCH_TIME}...")
                execute_predictive_switch()
        
        else:
            # Standard retrospective mode
            if current_time == config.EXECUTION_TIME and last_execution_date != current_date:
                last_execution_date = current_date
                # 10 Sec - 15 Min Random Delay to prevent all users attempting to access API at same time
                delay = random.randint(10, 900)
                send_notification(message=f"Octobot {config.BOT_VERSION} on. Initiating comparison in {delay/60:.1f} minutes")
                time.sleep(delay)
                run_tariff_compare()

        time.sleep(30)  # Check time every 30 seconds
