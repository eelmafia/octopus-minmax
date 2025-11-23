import time
import traceback
import math
from datetime import date, datetime, timedelta
import requests
import config
from account_info import AccountInfo
from notification import send_notification, send_batch_notification, debug_print
from queries import *
from tariff import TARIFFS
from query_service import QueryService
from decision_storage import save_decision, load_decision, clear_decision

query_service: QueryService
tariffs = []

# The version of the terms and conditions is required to accept the new tariff
def get_terms_version(product_code):
    query = get_terms_version_query.format(product_code=product_code)
    result = query_service.execute_gql_query(query)
    terms_version = result.get('termsAndConditionsForProduct', {}).get('version', "1.0").split('.')

    return({'major': int(terms_version[0]), 'minor': int(terms_version[1])})

def accept_new_agreement(product_code, enrolment_id):
    # get terms and conditions version
    version = get_terms_version(product_code)
    # accept terms and conditions
    query = accept_terms_query.format(account_number=config.ACC_NUMBER,
                                          enrolment_id=enrolment_id,
                                          version_major=version['major'],
                                          version_minor=version['minor'])
    result = query_service.execute_gql_query(query)
    return result.get('acceptTermsAndConditions', {}).get('acceptedVersion', "unknown version")



def get_acc_info() -> AccountInfo:
    query = account_query.format(acc_number=config.ACC_NUMBER)
    result = query_service.execute_gql_query(query)
    
    debug_print("Account query result structure:")
    debug_print(f"  Account key exists: {'account' in result}")
    if 'account' in result:
        debug_print(f"  Electricity agreements count: {len(result.get('account', {}).get('electricityAgreements', []))}")
        if config.DEBUG:
            import json
            debug_print(f"  Full account data: {json.dumps(result, indent=2, default=str)}")
    
    import_agreement = None
    for agreement in result.get("account", {}).get("electricityAgreements", []):
        meter_point = agreement.get("meterPoint", {})
        debug_print(f"  Checking agreement with direction: {meter_point.get('direction')}")
        if meter_point.get("direction") == "IMPORT":
            import_agreement = agreement
            debug_print("  Found IMPORT agreement")
            break
    
    if not import_agreement:
        error_msg = "ERROR: No IMPORT meter point found in account data"
        if config.DEBUG:
            error_msg += f"\nAvailable agreements: {[ag.get('meterPoint', {}).get('direction') for ag in result.get('account', {}).get('electricityAgreements', [])]}"
        raise Exception(error_msg)

    tariff = import_agreement.get("tariff")
    if not tariff:
        error_msg = "ERROR: No tariff information found for the IMPORT meter"
        if config.DEBUG:
            error_msg += f"\nImport agreement keys: {list(import_agreement.keys())}"
            error_msg += f"\nTariff value: {tariff}"
        raise Exception(error_msg)
    
    tariff_code = tariff.get("tariffCode")
    if not tariff_code:
        raise Exception("ERROR: No tariff code found for the IMPORT  tariff")
    
    curr_stdn_charge = tariff.get("standingCharge")
    if not curr_stdn_charge:
        raise Exception("ERROR: No standing charge found for the IMPORT meter tariff")
    
    region_code = tariff_code[-1]
    mpan = import_agreement.get("meterPoint", {}).get("mpan")
    if not mpan:
        raise Exception("ERROR: No MPAN found for the IMPORT meter")

    device_id = None
    meter_point = import_agreement.get("meterPoint", {})
    for meter in meter_point.get("meters", []):
        for device in meter.get("smartDevices", []):
            if "deviceId" in device:
                device_id = device["deviceId"]
                break
        if device_id:
            break
    
    if not device_id:
        raise Exception("ERROR: No device ID found for the IMPORT meter")
    
    matching_tariff = next((tariff for tariff in tariffs if tariff.is_tariff(tariff_code)), None)
    if matching_tariff is None:
        raise Exception(f"ERROR: Found no supported tariff for {tariff_code}")

    # Get consumption for today
    query = consumption_query.format(device_id=device_id, start_date=f"{date.today()}T00:00:00Z",
                                     end_date=f"{date.today()}T23:59:59Z")
    result = query_service.execute_gql_query(query)
    consumption = result['smartMeterTelemetry']

    return AccountInfo(matching_tariff, curr_stdn_charge, region_code, consumption, mpan)


def get_potential_tariff_rates(tariff, region_code, target_date=None):
    """
    Fetch tariff rates for a given tariff and region.
    
    Args:
        tariff: Display name of the tariff (e.g., "Agile Octopus", "Octopus Go")
        region_code: Region code (single character, e.g., "A", "B", etc.)
        target_date: Optional date object. If None, uses today's date.
    
    Returns:
        Tuple of (standing_charge_inc_vat, unit_rates_list, product_code)
    """
    if target_date is None:
        target_date = date.today()
    
    all_products = rest_query(f"{config.BASE_URL}/products/?brand=OCTOPUS_ENERGY&is_business=false")
    product = next((
        product for product in all_products['results']
        if product['display_name'] == tariff
           and product['direction'] == "IMPORT"
    ), None)

    product_code = product.get('code')

    if product_code is None:
        raise ValueError(f"No matching tariff found for {tariff}")

    # Use the self links to navigate to the tariff details
    product_link = next((
        item.get('href') for item in product.get('links', [])
        if item.get('rel', '').lower() == 'self'
    ), None)

    if not product_link:
        raise ValueError(f"Self link not found for tariff {product_code}.")

    tariff_details = rest_query(product_link)

    # Get the standing charge including VAT
    region_code_key = f'_{region_code}'
    filtered_region = tariff_details.get('single_register_electricity_tariffs', {}).get(region_code_key)

    if filtered_region is None:
        raise ValueError(f"Region code not found {region_code_key}.")

    region_tariffs = filtered_region.get('direct_debit_monthly') or filtered_region.get('varying')
    standing_charge_inc_vat = region_tariffs.get('standing_charge_inc_vat')

    if standing_charge_inc_vat is None:
        raise ValueError(f"Standing charge including VAT not found for region {region_code_key}.")

    # Find the link for standard unit rates
    region_links = region_tariffs.get('links', [])
    unit_rates_link = next((
        item.get('href') for item in region_links
        if item.get('rel', '').lower() == 'standard_unit_rates'
    ), None)

    if not unit_rates_link:
        raise ValueError(f"Standard unit rates link not found for region: {region_code_key}")

    # Get rates for the target date
    unit_rates_link_with_time = f"{unit_rates_link}?period_from={target_date}T00:00:00Z&period_to={target_date}T23:59:59Z"
    unit_rates = rest_query(unit_rates_link_with_time)

    return standing_charge_inc_vat, unit_rates.get('results', []), product_code


def rest_query(url):
    response = requests.get(url)
    if response.ok:
        data = response.json()
        return data
    else:
        raise Exception(f"ERROR: rest_query failed querying `{url}` with {response.status_code}")


def get_go_overnight_rate(region_code, target_date=None):
    """
    Fetch Octopus Go overnight rate from API.
    Returns the overnight rate in pence/kWh, or None if not found.
    """
    if target_date is None:
        target_date = date.today()
    
    try:
        standing_charge, unit_rates, product_code = get_potential_tariff_rates("Octopus Go", region_code, target_date)
        
        # Go has a specific overnight period (typically 00:30-04:30 or 00:30-05:30)
        # Find the overnight rate by looking for the cheapest rate in the early morning
        overnight_rates = []
        for rate in unit_rates:
            valid_from = rate.get('valid_from', '')
            # Check if this is in the overnight period (00:00-06:00)
            if 'T00:' in valid_from or 'T01:' in valid_from or 'T02:' in valid_from or \
               'T03:' in valid_from or 'T04:' in valid_from or 'T05:' in valid_from:
                overnight_rates.append(rate.get('value_inc_vat', 0))
        
        if overnight_rates:
            # Return the typical overnight rate (should be consistent)
            return min(overnight_rates)  # Use min in case there are variations
        return None
    except Exception as e:
        print(f"Error fetching Go overnight rate: {e}")
        return None


def compare_tariffs_for_battery(region_code, agile_rates, go_overnight_rate=None):
    """
    Compare Agile and Go tariffs for battery optimization.
    Simple comparison: find periods <= 120% of Go's rate.
    If multiple cheap periods exist on Agile, choose Agile. Otherwise compare costs.
    
    Args:
        region_code: Region code
        agile_rates: List of Agile rate periods for tomorrow (from API)
        go_overnight_rate: Go overnight rate in pence/kWh (optional, will fetch if None)
    
    Returns:
        Dict with keys: 'best_tariff' ('agile' or 'go'), 'reasoning', and analysis for each tariff
    """
    debug_print("=== Battery Tariff Comparison ===")
    debug_print(f"Battery Capacity: {config.BATTERY_CAPACITY_KWH} kWh")
    debug_print(f"Charge Rate: {config.BATTERY_CHARGE_RATE_KW} kW")
    debug_print(f"Charge Time Needed: {config.BATTERY_CAPACITY_KWH / config.BATTERY_CHARGE_RATE_KW:.2f} hours")
    
    # Get Go overnight rate from API if not provided
    if go_overnight_rate is None:
        tomorrow = date.today() + timedelta(days=1)
        debug_print(f"Fetching Go overnight rate for {tomorrow}...")
        go_overnight_rate = get_go_overnight_rate(region_code, tomorrow)
        if go_overnight_rate is None:
            raise Exception("Could not fetch Octopus Go overnight rate from API. Please ensure your API key has access to tariff rates.")
        debug_print(f"Fetched Go overnight rate: {go_overnight_rate}p/kWh")
    
    # Calculate cheap threshold: multiplier * Go's rate (default 120%)
    cheap_threshold = go_overnight_rate * config.CHEAP_RATE_MULTIPLIER
    threshold_percent = config.CHEAP_RATE_MULTIPLIER * 100
    debug_print(f"\nGo Tariff:")
    debug_print(f"  Overnight rate: {go_overnight_rate:.2f}p/kWh")
    debug_print(f"  Cheap threshold ({threshold_percent:.0f}%): {cheap_threshold:.2f}p/kWh")
    
    # Find Agile periods that are <= 120% of Go's rate
    debug_print(f"\nAgile Tariff Analysis:")
    debug_print(f"  Total rate periods: {len(agile_rates)}")
    
    cheap_periods = []
    for rate_period in agile_rates:
        rate_value = float(rate_period.get('value_inc_vat', 0))
        if rate_value <= cheap_threshold:
            valid_from = rate_period.get('valid_from', '')
            try:
                dt = datetime.fromisoformat(valid_from.replace('Z', '+00:00'))
                cheap_periods.append({
                    'rate': rate_value,
                    'datetime': dt,
                    'time': dt.strftime('%H:%M'),
                    'minutes': dt.hour * 60 + dt.minute
                })
            except:
                continue
    
    # Sort by time
    cheap_periods.sort(key=lambda x: x['minutes'])
    debug_print(f"  Cheap periods found (<= {cheap_threshold:.2f}p/kWh): {len(cheap_periods)}")
    
    if config.DEBUG and cheap_periods:
        debug_print("  All cheap periods:", indent=1)
        for p in cheap_periods[:20]:  # Show first 20
            debug_print(f"    {p['time']}: {p['rate']:.2f}p/kWh", indent=1)
        if len(cheap_periods) > 20:
            debug_print(f"    ... and {len(cheap_periods) - 20} more", indent=1)
    
    # Calculate minimum charge time needed (e.g., 80% of capacity)
    min_charge_hours = (config.BATTERY_CAPACITY_KWH * config.BATTERY_MIN_CHARGE_PERCENT) / config.BATTERY_CHARGE_RATE_KW
    min_charge_slots = math.ceil(min_charge_hours * 2)  # 30-min slots needed (round up)
    debug_print(f"  Minimum charge time: {min_charge_hours:.2f} hours ({min_charge_slots} slots)")
    
    # Calculate time needed for discharge (same as charge for simplicity, or could be separate config)
    discharge_time_hours = config.BATTERY_CAPACITY_KWH / config.BATTERY_CHARGE_RATE_KW
    min_gap_minutes = int(discharge_time_hours * 60)  # Minimum gap between charge opportunities
    
    # Group cheap periods into continuous charge opportunities
    charge_opportunities = []
    if cheap_periods:
        i = 0
        while i < len(cheap_periods):
            opportunity = [cheap_periods[i]]
            j = i + 1
            
            # Build continuous opportunity (periods within 30-60 minutes of each other)
            while j < len(cheap_periods):
                time_diff = cheap_periods[j]['minutes'] - opportunity[-1]['minutes']
                if time_diff <= 60:  # Within 1 hour (allowing for 30-min slots)
                    opportunity.append(cheap_periods[j])
                    j += 1
                else:
                    break
            
            # Only count if opportunity is long enough to charge battery
            if len(opportunity) >= min_charge_slots:
                avg_rate = sum(p['rate'] for p in opportunity) / len(opportunity)
                duration_hours = len(opportunity) * 0.5
                charge_opportunities.append({
                    'periods': opportunity,
                    'start_time': opportunity[0]['time'],
                    'end_time': opportunity[-1]['time'],
                    'start_minutes': opportunity[0]['minutes'],
                    'end_minutes': opportunity[-1]['minutes'],
                    'duration_hours': duration_hours,
                    'avg_rate': avg_rate,
                    'slot_count': len(opportunity)
                })
                debug_print(f"  Charge opportunity: {opportunity[0]['time']}-{opportunity[-1]['time']} "
                           f"({duration_hours:.1f}h, {len(opportunity)} slots, avg: {avg_rate:.2f}p/kWh)", indent=1)
            
            i = j
    
    debug_print(f"  Viable charge opportunities: {len(charge_opportunities)}")
    
    # Check if opportunities are spaced far enough apart for multiple cycles
    multiple_cycles_possible = False
    if len(charge_opportunities) > 1:
        # Sort by start time
        charge_opportunities.sort(key=lambda x: x['start_minutes'])
        for i in range(len(charge_opportunities) - 1):
            gap = charge_opportunities[i+1]['start_minutes'] - charge_opportunities[i]['end_minutes']
            if gap >= min_gap_minutes:
                multiple_cycles_possible = True
                debug_print(f"  Multiple cycles possible: gap of {gap/60:.1f}h between opportunities", indent=1)
                break
    
    # Decision logic: Compare Agile vs Go
    # - If multiple viable charge opportunities with proper spacing, choose Agile
    # - If one opportunity, compare price with Go
    # - Otherwise, choose Go
    
    best_tariff = 'go'  # Default
    reasoning_parts = []
    reasoning_parts.append(f"Go: Overnight rate {go_overnight_rate:.2f}p/kWh")
    
    # Evaluate Agile
    agile_score = 0
    if len(charge_opportunities) > 1 and multiple_cycles_possible:
        agile_score = 2  # Multiple cycles
    elif len(charge_opportunities) == 1:
        if charge_opportunities[0]['avg_rate'] < go_overnight_rate:
            agile_score = 1  # Single cheaper opportunity
    
    # Choose best tariff
    if agile_score == 2:
        # Multiple cycles available - choose Agile
        best_tariff = 'agile'
        avg_rate = sum(opp['avg_rate'] for opp in charge_opportunities) / len(charge_opportunities)
        reasoning_parts.append(f"Agile: {len(charge_opportunities)} charge opportunities (avg: {avg_rate:.2f}p/kWh)")
        reasoning_parts.append(f"Decision: Agile (multiple charge opportunities with proper spacing)")
    elif agile_score == 1:
        # Single cheaper opportunity - choose Agile
        agile_rate = charge_opportunities[0]['avg_rate']
        best_tariff = 'agile'
        reasoning_parts.append(f"Agile: 1 charge opportunity at {agile_rate:.2f}p/kWh (cheaper than Go)")
        reasoning_parts.append(f"Decision: Agile (cheaper than Go)")
    else:
        # No viable opportunities
        best_tariff = 'go'
        if cheap_periods:
            min_agile_rate = min(p['rate'] for p in cheap_periods)
            reasoning_parts.append(f"Agile: No periods long enough to charge (minimum rate: {min_agile_rate:.2f}p/kWh)")
        else:
            min_agile_rate = min(float(r.get('value_inc_vat', 999)) for r in agile_rates) if agile_rates else 999
            reasoning_parts.append(f"Agile: No cheap periods (minimum: {min_agile_rate:.2f}p/kWh)")
        
        reasoning_parts.append(f"Decision: Go (no viable alternatives)")
    
    reasoning = "\n".join(reasoning_parts)
    
    debug_print(f"\n=== Comparison Result ===")
    debug_print(f"Best tariff: {best_tariff.upper()}")
    debug_print(f"Agile opportunities: {len(charge_opportunities)}")
    
    return {
        'best_tariff': best_tariff,
        'reasoning': reasoning,
        'agile_cheap_periods': len(cheap_periods),
        'agile_charge_opportunities': len(charge_opportunities),
        'go_overnight_rate': go_overnight_rate,
        'cheap_threshold': cheap_threshold,
        'cheap_periods': cheap_periods,
        'charge_opportunities': charge_opportunities
    }


def calculate_potential_costs(consumption_data, rate_data):
    period_costs = []
    for consumption in consumption_data:
        read_time = consumption['readAt'].replace('+00:00', 'Z')
        matching_rate = next(
            rate for rate in rate_data
            # Flexible has no end time, so default to the end of time
            if rate['valid_from'] <= read_time <= (rate.get('valid_to') or "9999-12-31T23:59:59Z")
            # DIRECT_DEBIT is for flexible that has different price for direct debit or not
            and rate['payment_method'] in [None, "DIRECT_DEBIT"]
        )

        consumption_kwh = float(consumption['consumptionDelta']) / 1000
        cost = float("{:.4f}".format(consumption_kwh * matching_rate['value_inc_vat']))

        period_costs.append({
            'period_end': read_time,
            'consumption_kwh': consumption_kwh,
            'rate': matching_rate['value_inc_vat'],
            'calculated_cost': cost,
        })
    return period_costs

def switch_tariff(target_product_code, mpan, target_date=None):
    """
    Switch to a new tariff.
    
    Args:
        target_product_code: Product code of the target tariff
        mpan: MPAN of the meter
        target_date: Optional date for the switch. If None, uses today.
    
    Returns:
        Enrolment ID if successful, None otherwise
    """
    if target_date is None:
        target_date = date.today()
    
    query = switch_query.format(account_number=config.ACC_NUMBER, mpan=mpan, product_code=target_product_code, change_date=target_date)
    result = query_service.execute_gql_query(query)
    return result.get("startOnboardingProcess", {}).get("productEnrolment", {}).get("id")

def verify_new_agreement():
    query = account_query.format(acc_number=config.ACC_NUMBER)
    result = query_service.execute_gql_query(query)
    today = datetime.now().date()
    valid_from = next((datetime.fromisoformat(agreement['validFrom']).date()
                      for agreement in result['account']['electricityAgreements']
                      if 'validFrom' in agreement),None)

    # For some reason, sometimes the agreement has no end date, so I'm not sure if this bit is still relevant?
    # valid_to = datetime.fromisoformat(result['account']['electricityAgreements'][0]['validTo']).date()
    # next_year = valid_from.replace(year=valid_from.year + 1)
    return valid_from == today

def compare_and_switch():
    welcome_message = "DRY RUN: " if config.DRY_RUN else ""
    welcome_message += "Starting comparison of today's costs..."
    send_notification(welcome_message)

    account_info = get_acc_info()
    current_tariff = account_info.current_tariff

    # Total consumption cost
    total_con_cost = sum(float(entry['costDeltaWithTax'] or 0) for entry in account_info.consumption)
    total_curr_cost = total_con_cost + account_info.standing_charge

    # Total consumption
    total_wh = sum(float(consumption['consumptionDelta']) for consumption in account_info.consumption)
    total_kwh = total_wh / 1000  # Convert watt-hours to kilowatt-hours

    # Print out consumption on current tariff
    summary = f"Total Consumption today: {total_kwh:.4f} kWh\n"
    summary += f"Current tariff {current_tariff.display_name}: £{total_curr_cost / 100:.2f} " \
               f"(£{total_con_cost / 100:.2f} con + " \
               f"£{account_info.standing_charge / 100:.2f} s/c)\n"

    # Track costs key: Tariff, value: total cost in pence
    # Add current tariff
    costs = {current_tariff: total_curr_cost}

    # Calculate costs of other tariffs
    for tariff in tariffs:
        if tariff == current_tariff:
            continue  # Skip if you're already on that tariff

        try:
            (potential_std_charge, potential_unit_rates, potential_product_code) = \
                get_potential_tariff_rates(tariff.api_display_name, account_info.region_code)
            tariff.product_code = potential_product_code
            potential_costs = calculate_potential_costs(account_info.consumption, potential_unit_rates)

            total_tariff_consumption_cost = sum(period['calculated_cost'] for period in potential_costs)
            total_tariff_cost = total_tariff_consumption_cost + potential_std_charge

            costs[tariff] = total_tariff_cost
            summary += f"Potential cost on {tariff.display_name}: £{total_tariff_cost / 100:.2f} " \
                       f"(£{total_tariff_consumption_cost / 100:.2f} con + " \
                       f"£{potential_std_charge / 100:.2f} s/c)\n"

        except Exception as e:
            print(f"Error finding prices for tariff: {tariff.id}. {e}")
            summary += f"No cost for {tariff.display_name}\n"
            costs[tariff] = None

    # Filter the dictionary to only include tariffs where the `switchable` attribute is True
    switchable_tariffs = {t: cost for t, cost in costs.items() if t.switchable and cost is not None}

    # Find the cheapest tariffs that is in the list and switchable
    curr_cost = costs.get(current_tariff, float('inf'))
    cheapest_tariff = min(switchable_tariffs, key=switchable_tariffs.get)
    cheapest_cost = costs[cheapest_tariff]

    if cheapest_tariff == current_tariff:
        send_notification(
            f"{summary}\nYou are already on the cheapest tariff: {cheapest_tariff.display_name} at £{cheapest_cost / 100:.2f}")
        return

    savings = curr_cost - cheapest_cost

    # Only switch if the savings are greater than or equal to the SWITCH_THRESHOLD parameter.
    if savings >= config.SWITCH_THRESHOLD:
        switch_message = f"{summary}\nInitiating Switch to {cheapest_tariff.display_name}"
        send_notification(switch_message)

        if config.DRY_RUN:
            dry_run_message = "DRY RUN: Not going through with switch today."
            send_notification(dry_run_message)
            return None

        if cheapest_tariff.product_code is None:
            send_notification("ERROR: product_code is missing.")
            return 
        
        if account_info.mpan is None:
            send_notification("ERROR: mpan is missing.")
            return  
        
        enrolment_id = switch_tariff(cheapest_tariff.product_code, account_info.mpan)
        if enrolment_id is None:
            send_notification("ERROR: couldn't get enrolment ID")
            return
        else:
            send_notification("Tariff switch requested successfully.")
        # Give octopus some time to generate the agreement
        time.sleep(60)
        accepted_version = accept_new_agreement(cheapest_tariff.product_code, enrolment_id)
        send_notification("Accepted agreement (v.{version}). Switch successful.".format(version=accepted_version))

        verified = verify_new_agreement()
        if not verified:
            send_notification("Verification failed, waiting 20 seconds and trying again...")
            time.sleep(20)
            verified = verify_new_agreement()  # Retry
            
            if verified:
                send_notification("Verified new agreement successfully. Process finished.")
            else:
                send_notification(f"Unable to verify new agreement after retry. Please check your account and emails.\n" \
                 f"https://octopus.energy/dashboard/new/accounts/{config.ACC_NUMBER}/messages")
    else:
        send_notification(f"{summary}\nNot switching today.")


def load_tariffs_from_ids(tariff_ids: str):
    global tariffs

    # Convert the input string into a set of lowercase tariff IDs
    requested_ids = set(tariff_ids.lower().split(","))

    # Get all predefined tariffs from the Tariffs class
    all_tariffs = TARIFFS

    # Match requested tariffs to predefined ones
    matched_tariffs = []
    for tariff_id in requested_ids:
        matched = next((t for t in all_tariffs if t.id == tariff_id), None)

        if matched is not None:
            matched_tariffs.append(matched)
        else:
            send_notification(f"Warning: No tariff found for ID '{tariff_id}'")

    tariffs = matched_tariffs


def get_tomorrow_tariff_rates(tariff_name, region_code, retry_if_missing=True):
    """
    Fetch tomorrow's rates for a given tariff.
    
    Args:
        tariff_name: Display name of the tariff (e.g., "Agile Octopus", "Octopus Go")
        region_code: Region code
        retry_if_missing: If True and rates not available, will indicate retry needed
    
    Returns:
        Tuple of (standing_charge, unit_rates_list, product_code, needs_retry) or (None, None, None, False/True)
    """
    tomorrow = date.today() + timedelta(days=1)
    debug_print(f"Fetching {tariff_name} rates for {tomorrow} (region {region_code})...")
    
    try:
        standing_charge, unit_rates, product_code = get_potential_tariff_rates(tariff_name, region_code, tomorrow)
        
        if not unit_rates or len(unit_rates) == 0:
            debug_print(f"No {tariff_name} rates returned (may not be published yet)")
            if retry_if_missing:
                return None, None, None, True  # Indicate retry needed
            return None, None, None, False
        
        debug_print(f"Successfully fetched {len(unit_rates)} {tariff_name} rate periods")
        if config.DEBUG:
            # Show rate range
            rates = [float(r.get('value_inc_vat', 0)) for r in unit_rates]
            debug_print(f"  Rate range: {min(rates):.2f}p - {max(rates):.2f}p/kWh")
            debug_print(f"  Average rate: {sum(rates)/len(rates):.2f}p/kWh")
        
        return standing_charge, unit_rates, product_code, False
    except Exception as e:
        debug_print(f"Error fetching {tariff_name} rates: {e}", indent=1)
        if retry_if_missing:
            return None, None, None, True
        return None, None, None, False


def get_tomorrow_agile_rates(region_code, retry_if_missing=True):
    """
    Fetch tomorrow's Agile rates with retry logic.
    Wrapper for get_tomorrow_tariff_rates for backward compatibility.
    """
    return get_tomorrow_tariff_rates("Agile Octopus", region_code, retry_if_missing)


def make_predictive_decision():
    """
    Make a decision about which tariff to use tomorrow based on battery optimization.
    This runs at DECISION_TIME (e.g., 17:00) to check tomorrow's rates.
    """
    global query_service
    try:
        debug_print("=" * 60)
        debug_print("MAKING PREDICTIVE DECISION")
        debug_print("=" * 60)
        
        # Ensure query service is initialized
        if query_service is None:
            debug_print("Initializing query service...")
            query_service = QueryService(config.API_KEY, config.BASE_URL)
        if not tariffs:
            debug_print(f"Loading tariffs: {config.TARIFFS}")
            load_tariffs_from_ids(config.TARIFFS)
        
        debug_print("Fetching account information...")
        try:
            account_info = get_acc_info()
            region_code = account_info.region_code
            mpan = account_info.mpan
            debug_print(f"Region code: {region_code}")
            debug_print(f"Current tariff: {account_info.current_tariff.display_name}")
        except Exception as e:
            send_notification(f"ERROR: Could not fetch account information. Please ensure your account is properly set up and your API key has the correct permissions. Error: {e}", error=True)
            raise Exception(f"Cannot proceed without account information. Error: {e}")
        
        send_notification("Predictive mode: Checking tomorrow's rates...")
        
        # Try to fetch tomorrow's Agile rates
        standing_charge, agile_rates, agile_product_code, needs_retry = get_tomorrow_agile_rates(region_code)
        
        if needs_retry:
            current_hour = datetime.now().hour
            if current_hour < 23:
                send_notification("Tomorrow's Agile rates not yet available. Will retry in 1 hour.")
                return False  # Indicate retry needed
            else:
                send_notification("ERROR: Tomorrow's Agile rates still not available. Cannot make decision.")
                return False
        
        if agile_rates is None or len(agile_rates) == 0:
            send_notification("ERROR: Could not fetch tomorrow's Agile rates.")
            return False
        
        # Get Go tariff for product code
        go_tariff = next((t for t in tariffs if t.id == "go"), None)
        if not go_tariff:
            send_notification("ERROR: Go tariff not found in configured tariffs.")
            return False
        
        try:
            _, _, go_product_code = get_potential_tariff_rates("Octopus Go", region_code, date.today() + timedelta(days=1))
            go_tariff.product_code = go_product_code
        except Exception as e:
            send_notification(f"Warning: Could not fetch Go product code: {e}")
        
        # Compare tariffs for battery optimization
        comparison = compare_tariffs_for_battery(region_code, agile_rates)
        
        # Determine which tariff to choose
        if comparison['best_tariff'] == 'agile':
            chosen_tariff = next((t for t in tariffs if t.id == "agile"), None)
            chosen_product_code = agile_product_code
        else:
            chosen_tariff = go_tariff
            chosen_product_code = go_tariff.product_code
        
        if not chosen_tariff:
            send_notification("ERROR: Could not find chosen tariff.")
            return False
        
        if not chosen_product_code:
            send_notification("ERROR: Product code missing for chosen tariff.")
            return False
        
        if not mpan:
            send_notification("WARNING: MPAN not available. Decision made but switch cannot be executed until account is fully set up.")
        
        # Save decision
        tomorrow = date.today() + timedelta(days=1)
        decision_data = {
            'target_date': tomorrow.isoformat(),
            'chosen_tariff_id': chosen_tariff.id,
            'chosen_tariff_name': chosen_tariff.display_name,
            'chosen_product_code': chosen_product_code,
            'reasoning': comparison['reasoning'],
            'agile_cheap_periods': comparison['agile_cheap_periods'],
            'agile_charge_opportunities': comparison['agile_charge_opportunities'],
            'go_overnight_rate': comparison['go_overnight_rate'],
            'mpan': mpan
        }
        save_decision(decision_data)
        
        # Send notification
        decision_msg = f"Predictive Decision for {tomorrow}:\n"
        decision_msg += f"Chosen: {chosen_tariff.display_name}\n"
        decision_msg += f"{comparison['reasoning']}\n"
        decision_msg += f"Switch will execute at {config.SWITCH_TIME}"
        send_notification(decision_msg)
        
        return True
        
    except Exception as e:
        send_notification(f"ERROR in predictive decision: {traceback.format_exc()}", error=True)
        return False


def execute_predictive_switch():
    """
    Execute the stored tariff switch decision.
    This runs at SWITCH_TIME (e.g., 00:01) to actually perform the switch.
    """
    global query_service
    try:
        # Ensure query service is initialized
        if query_service is None:
            query_service = QueryService(config.API_KEY, config.BASE_URL)
        
        decision = load_decision()
        
        if not decision:
            send_notification("No stored decision found. Skipping switch.")
            return
        
        target_date_str = decision.get('target_date')
        target_date = datetime.fromisoformat(target_date_str).date()
        today = date.today()
        
        # Only switch if decision is for today
        if target_date != today:
            send_notification(f"Stored decision is for {target_date}, but today is {today}. Skipping switch.")
            return
        
        chosen_product_code = decision.get('chosen_product_code')
        mpan = decision.get('mpan')
        chosen_tariff_name = decision.get('chosen_tariff_name', 'Unknown')
        
        if not chosen_product_code or not mpan:
            send_notification("ERROR: Missing product code or MPAN in stored decision.")
            return
        
        send_notification(f"Executing switch to {chosen_tariff_name} for {target_date}...")
        
        if config.DRY_RUN:
            send_notification("DRY RUN: Not executing switch.")
            clear_decision()
            return
        
        enrolment_id = switch_tariff(chosen_product_code, mpan, target_date)
        
        if enrolment_id is None:
            send_notification("ERROR: Could not get enrolment ID.")
            return
        
        send_notification("Tariff switch requested successfully.")
        
        # Give Octopus time to generate the agreement
        time.sleep(60)
        
        accepted_version = accept_new_agreement(chosen_product_code, enrolment_id)
        send_notification(f"Accepted agreement (v.{accepted_version}). Switch successful.")
        
        # Clear the decision
        clear_decision()
        
    except Exception as e:
        send_notification(f"ERROR executing predictive switch: {traceback.format_exc()}", error=True)


def run_tariff_compare():
    try:
        global query_service
        query_service = QueryService(config.API_KEY, config.BASE_URL)
        load_tariffs_from_ids(config.TARIFFS)
        if query_service is not None:
            if config.PREDICTIVE_MODE:
                # Predictive mode uses different flow (handled by scheduler)
                send_notification("Predictive mode is enabled. Use scheduler for decision/switch phases.")
            else:
                compare_and_switch()
        else:
            raise Exception("ERROR: setup_gql has failed")
    except:
        send_notification(message=traceback.format_exc(), title="Octobot Error", error=True)
    finally:
        if config.BATCH_NOTIFICATIONS:
            send_batch_notification()
