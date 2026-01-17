import time
from datetime import date, datetime, timezone
from typing import List, Dict, Optional, Tuple
import random
import config
import config_manager
import mqtt_publisher
from account_info import AccountInfo
from account_manager import AccountManager
from queries import *
from tariff import Tariff, TARIFFS
from query_service import QueryService
from comparison_engine import ComparisonEngine, ComparisonResult
from notification_service import NotificationService
import logging
logger = logging.getLogger('octobot.bot_orchestrator')

def get_timestamp():
    return datetime.now().strftime("%d/%m/%Y %H:%M")

class BotOrchestrator:
    def __init__(self):
        logger.debug(f"Initialising {__class__.__name__}")
        self.query_service = None
        self.account_manager = None
        self.tariffs = []
        self.last_execution_datetime = None
        self.notification_service = None

    def start(self) -> None:
        self.notification_service = NotificationService(config.NOTIFICATION_URLS, config.BATCH_NOTIFICATIONS)
        ns = self.notification_service

        mode_msg = "ONE_OFF mode enabled" if config.ONE_OFF_RUN else f"Scheduled mode, running at {config.EXECUTION_TIME}"
        ns.send_notification(f"[{get_timestamp()}] Octobot {config.BOT_VERSION} - {mode_msg} \n Check port {config.WEB_PORT} for dashboard.")

        while True:
            if config.ONE_OFF_RUN and not config.ONE_OFF_EXECUTED:
                ns.send_notification(f"[{get_timestamp()}] Octobot {config.BOT_VERSION} - Running one-off comparison")
                config_manager.reset_one_off_run()
                self._run_tariff_compare()
            elif not config.ONE_OFF_RUN:
                now = datetime.now()
                current_time = now.strftime("%H:%M")
                current_minute = now.replace(second=0, microsecond=0)  # Datetime object at minute precision
                if current_time == config.EXECUTION_TIME and self.last_execution_datetime != current_minute:
                    self.last_execution_datetime = current_minute
                    delay = random.randint(10, 900)
                    ns.send_notification(f"[{get_timestamp()}] Octobot {config.BOT_VERSION} - Initiating comparison in {delay/60:.1f} minutes")
                    time.sleep(delay)
                    self._run_tariff_compare()

            time.sleep(30)

    def _initialize(self) -> None:
        logger.debug(f"{__name__}")
        self._load_tariffs_from_ids(config.TARIFFS)
        self.query_service = QueryService(config.API_KEY, config.BASE_URL)
        self.account_manager = AccountManager.get_instance(self.query_service, self.tariffs)


    def _load_tariffs_from_ids(self, tariff_ids: str) -> None:
        """Load tariffs from comma-separated string of IDs."""
        requested_ids = set(tariff_ids.lower().split(","))
        logger.debug(f" Requested tariff IDs - {requested_ids}")
        matched_tariffs = []
        for tariff_id in requested_ids:
            matched = next((t for t in TARIFFS if t.id == tariff_id), None)

            if matched is not None:
                matched_tariffs.append(matched)
            else:
                self.notification_service.send_notification(f"Warning: No tariff found for ID '{tariff_id}'")

        self.tariffs = matched_tariffs

    def _run_tariff_compare(self) -> None:
        ns = self.notification_service
        try:
            self._initialize()
            if self.query_service is None:
                raise Exception("ERROR: QueryService initialization failed")

            self._compare_and_switch()
        except Exception as e:
            error_text = str(e).strip() or repr(e) or "Unknown error"
            logger.exception("Comparison failed: %s", error_text)
            ns.send_notification(message=error_text, title="Octobot Error", is_error=True)
        finally:
            if config.BATCH_NOTIFICATIONS:
                ns.send_batch_notification()

    def _format_comparison_summary(self, result: ComparisonResult) -> str:
        lines = []

        # Current consumption
        current = result.current_tariff_comparison
        if current.cost_breakdown:
            lines.append(f"Total Consumption today: {current.cost_breakdown.total_kwh:.4f} kWh")
            lines.append(
                f"Current tariff {current.tariff.display_name}: "
                f"£{current.cost_breakdown.total_cost_pounds:.2f} "
                f"(£{current.cost_breakdown.consumption_cost_pounds:.2f} con + "
                f"£{current.cost_breakdown.standing_charge_pounds:.2f} s/c)"
            )

        for comparison in result.alternative_comparisons:
            if comparison.is_valid:
                lines.append(
                    f"Potential cost on {comparison.tariff.display_name}: "
                    f"£{comparison.cost_breakdown.total_cost_pounds:.2f} "
                    f"(£{comparison.cost_breakdown.consumption_cost_pounds:.2f} con + "
                    f"£{comparison.cost_breakdown.standing_charge_pounds:.2f} s/c)"
                )
            else:
                lines.append(f"No cost for {comparison.tariff.display_name}")

        return "\n".join(lines)

    def _compare_and_switch(self) -> None:
        ns = self.notification_service
        only_results = config.ONLY_RESULTS_NOTIFICATIONS
        welcome_message = f"{'DRY RUN: ' if config.DRY_RUN else ''}Starting comparison of today's costs..."
        ns.send_notification(welcome_message)

        account_info = self.account_manager.fetch_current_account_info()

        comparison_engine = ComparisonEngine(self.query_service)
        results = comparison_engine.compare_tariffs(account_info, self.tariffs)

        summary = self._format_comparison_summary(results)
        if not only_results:
            ns.send_notification(message=summary, is_results=True)

        switched = False
        switch_error = False
        outcome_message = None
        if results.should_switch:
            switch_message = f"Initiating Switch to {results.cheapest_tariff.display_name}"
            if not only_results:
                ns.send_notification(switch_message)
            if config.DRY_RUN:
                outcome_message = "DRY RUN: Not going through with switch today."
                if not only_results:
                    ns.send_notification(outcome_message)
            else:
                try:
                    switched = self._execute_switch(results.cheapest_tariff, account_info)
                    if switched:
                        outcome_message = f"Switched to {results.cheapest_tariff.display_name}."
                    else:
                        outcome_message = f"Switch to {results.cheapest_tariff.display_name} failed."
                except Exception as exc:
                    switch_error = True
                    outcome_message = f"ERROR: Switch failed: {exc}"
                    if not only_results:
                        ns.send_notification(outcome_message)
        else:
            if results.cheapest_tariff == results.current_tariff_comparison.tariff:
                message = (f"You are already on the cheapest tariff: "
                          f"{results.cheapest_tariff.display_name} at "
                          f"£{results.current_tariff_comparison.cost_breakdown.total_cost_pounds:.2f}")
            else:
                message = (f"Not switching today - savings of (£{results.potential_savings / 100:.2f}) "
                           f"on the cheapest tariff {results.cheapest_tariff.display_name} are below your "
                           f"threshold of £{config.SWITCH_THRESHOLD / 100:.2f}")
            outcome_message = message
            if not only_results:
                ns.send_notification(message)

        if only_results:
            combined = summary
            if outcome_message:
                combined = f"{combined}\n{outcome_message}"
            ns.send_notification(message=combined, is_results=True)

        self._persist_last_run(results, switched, switch_error)

    def _persist_last_run(self, results: ComparisonResult, switched: bool, switch_error: bool) -> None:
        def _comparison_payload(comparison):
            payload = {
                'id': comparison.tariff.id,
                'name': comparison.tariff.display_name,
                'valid': comparison.is_valid,
            }
            if comparison.is_valid:
                payload.update({
                    'total_pence': comparison.cost_breakdown.total_cost,
                    'consumptioncost_pence': comparison.cost_breakdown.consumption_cost,
                    'standingcharge_pence': comparison.cost_breakdown.standing_charge,
                })
            else:
                payload['error'] = comparison.error
            return payload

        current = results.current_tariff_comparison
        total_consumption_kwh = None
        if current.is_valid:
            total_consumption_kwh = current.cost_breakdown.total_kwh

        def _decision_reason():
            if switch_error:
                return "error"
            if switched:
                return None
            if config.DRY_RUN and results.should_switch:
                return "dry_run"
            if results.cheapest_tariff == current.tariff:
                return "already_cheapest"
            return "threshold_not_met"

        def _comparison_for_tariff(tariff):
            if tariff is None:
                return None
            if current.tariff == tariff:
                return current
            return next((c for c in results.alternative_comparisons if c.tariff == tariff), None)

        chosen_tariff = results.cheapest_tariff if switched else current.tariff
        chosen_comparison = _comparison_for_tariff(chosen_tariff)
        cost_today = None
        if chosen_comparison and chosen_comparison.is_valid:
            cost_today = {
                'consumptioncost_pence': chosen_comparison.cost_breakdown.consumption_cost,
                'standingcharge_pence': chosen_comparison.cost_breakdown.standing_charge,
                'totalcost_pence': chosen_comparison.cost_breakdown.total_cost,
            }

        payload = {
            'decision': {
                'action': "switched" if switched else "not_switched",
                'reason': _decision_reason(),
                'dry_run': config.DRY_RUN,
                'savings_pence': results.potential_savings,
                'threshold_pence': config.SWITCH_THRESHOLD,
                'cheapest_tariff_id': results.cheapest_tariff.id if results.cheapest_tariff else None,
                'cost_today': cost_today,
            },
            'datetime': datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            'totalconsumption_kwh': total_consumption_kwh,
            'currenttariff': _comparison_payload(current),
            'comparisons': [_comparison_payload(c) for c in results.alternative_comparisons],
        }
        config_manager.persist_last_run(payload)
        mqtt_publisher.publish_results(payload)

    def _execute_switch(self, target_tariff: Tariff, account_info: AccountInfo) -> bool:
        ns = self.notification_service

        if not target_tariff.product_code:
            ns.send_notification("ERROR: product_code is missing.")
            return False

        enrolment_id = self.account_manager.initiate_tariff_switch(target_tariff.product_code)
        if not enrolment_id:
            ns.send_notification("ERROR: Couldn't get enrolment ID")
            return False

        wait_time = 120
        ns.send_notification(f"Tariff switch requested successfully. Waiting {wait_time}s before attempting to accept new agreement.")

        # Give octopus some time to generate the agreement
        time.sleep(wait_time)
        accepted_version = self.account_manager.accept_new_agreement(target_tariff.product_code, enrolment_id)
        ns.send_notification(f"Accepted agreement (v.{accepted_version}). Switch successful.")

        verified = self.account_manager.verify_new_agreement_status()
        if not verified:
            ns.send_notification("Verification failed, waiting 20 seconds and trying again...")
            time.sleep(60)
            verified = self.account_manager.verify_new_agreement_status() # Retry
            if verified:
                ns.send_notification("Verified new agreement successfully. Process finished.")
            else:
                ns.send_notification(
                    f"Unable to verify new agreement after retry. "
                    f"Please check your account and emails.\n"
                    f"https://octopus.energy/dashboard/new/accounts/{config.ACC_NUMBER}/messages"
                )
                return False
        return True
