import time
import traceback
from datetime import date, datetime
import requests
import config
from account_info import AccountInfo
from notification import send_notification, send_batch_notification
from queries import *
from tariff import TARIFFS
from query_service import QueryService

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
    import_agreement = None
    for agreement in result.get("account", {}).get("electricityAgreements", []):
        meter_point = agreement.get("meterPoint", {})
        if meter_point.get("direction") == "IMPORT":
            import_agreement = agreement
            break

    if not import_agreement:
        raise Exception("ERROR: No IMPORT meter point found in account data")

    tariff = import_agreement.get("tariff")
    if not tariff:
        raise Exception("ERROR: No tariff information found for the IMPORT meter")

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


def get_potential_tariff_rates(tariff, region_code):
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

    # Get today's rates
    today = date.today()
    unit_rates_link_with_time = f"{unit_rates_link}?period_from={today}T00:00:00Z&period_to={today}T23:59:59Z"
    unit_rates = rest_query(unit_rates_link_with_time)

    return standing_charge_inc_vat, unit_rates.get('results', []), product_code


def rest_query(url):
    response = requests.get(url)
    if response.ok:
        data = response.json()
        return data
    else:
        raise Exception(f"ERROR: rest_query failed querying `{url}` with {response.status_code}")


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

def switch_tariff(target_product_code, mpan):
    change_date = date.today()
    query = switch_query.format(account_number=config.ACC_NUMBER, mpan=mpan, product_code=target_product_code, change_date=change_date)
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


def run_tariff_compare():
    try:
        global query_service
        query_service = QueryService(config.API_KEY, config.BASE_URL)
        load_tariffs_from_ids(config.TARIFFS)
        if query_service is not None:
            compare_and_switch()
        else:
            raise Exception("ERROR: setup_gql has failed")
    except:
        send_notification(message=traceback.format_exc(), title="Octobot Error", error=True)
    finally:
        if config.BATCH_NOTIFICATIONS:
            send_batch_notification()