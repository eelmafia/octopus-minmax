import time
import traceback
from datetime import date, datetime

import requests
from apprise import Apprise
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from playwright.sync_api import sync_playwright

import config

gql_transport: AIOHTTPTransport
gql_client: Client
opposite_tariff = {
    "AGILE": "GO",
    "GO": "AGILE"
}

token_query = """mutation {{
	obtainKrakenToken(input: {{ APIKey: "{api_key}" }}) {{
	    token
	}}
}}"""

# I have no idea if versionMajor or versionMinor has an impact???
accept_terms_query = """mutation {{
    acceptTermsAndConditions(input: {{
        accountNumber: "{account_number}",
        enrolmentId: "{enrolment_id}",
        termsVersion: {{
            versionMajor: 1,
            versionMinor: 1
        }}
    }}) 
    {{
    acceptedVersion
  }}
}}"""

consumption_query = """query {{
    smartMeterTelemetry(
        deviceId: "{device_id}"
        grouping: HALF_HOURLY
        start: "{start_date}"
        end: "{end_date}"
    ) {{
    readAt
    consumptionDelta
    costDeltaWithTax
  }}
}}"""

account_query = """query{{
    account(
        accountNumber: "{acc_number}"
    ) {{
    electricityAgreements(active: true) {{
        validFrom
        validTo
        meterPoint {{
            meters(includeInactive: false) {{
                smartDevices {{
                    deviceId
                }}
            }}
            mpan
        }}
        tariff {{
            ... on HalfHourlyTariff {{
                id
                productCode
                tariffCode
                productCode
                standingCharge
                }}
            }}
        }}
    }}
}}"""
enrolment_query = """query {{
    productEnrolments(accountNumber: "{acc_number}") {{
        id
        status
        product {{
            code
            displayName
        }}
    stages {{
      name
      status
      steps {{
        displayName
        status
        updatedAt
      }}
    }}
  }}
}}"""


def send_notification(message, title="Octobot"):
    """Sends a notification using Apprise.

    Args:
        message (str): The message to send.
        title (str, optional): The title of the notification. Defaults to "Octobot".
    """
    print(message)

    apobj = Apprise()

    if config.NOTIFICATION_URLS:
        for url in config.NOTIFICATION_URLS.split(','):
            apobj.add(url.strip())

    if not apobj:
        print("No notification services configured. Check config.NOTIFICATION_URLS.")
        return

    # Check if any of the URLs are Discord URLs, and only wrap the message in backticks if *only* Discord is present
    urls = config.NOTIFICATION_URLS.split(',') if config.NOTIFICATION_URLS else []  # Get the URLs, handle None
    is_only_discord = all("discord" in url.lower() for url in urls)

    if is_only_discord:
        message = f"`{message}`"

    apobj.notify(body=message, title=title)


def accept_new_agreement():
    query = gql(enrolment_query.format(acc_number=config.ACC_NUMBER))
    result = gql_client.execute(query)
    try:
        enrolment_id = next(entry['id'] for entry in result['productEnrolments'] if entry['status'] == "IN_PROGRESS")
    except StopIteration:
        # Strangely sometimes the enrolment skips 'IN_PROGRESS' and just auto-accepts, so we check if it's completed with today's date
        today = datetime.now().date()

        for entry in result['productEnrolments']:
            for stage in entry['stages']:
                if stage['name'] == 'post-enrolment':
                    last_step_date = datetime.fromisoformat(
                        stage['steps'][-1]['updatedAt'].replace('Z', '+00:00')).date()
                    if last_step_date == today and stage['status'] == 'COMPLETED':
                        send_notification("Post-enrolment automatically completed with today's date.")
                        return

        raise Exception("ERROR: No completed post-enrolment found today and no in-progress enrolment.")
    query = gql(accept_terms_query.format(account_number=config.ACC_NUMBER, enrolment_id=enrolment_id))
    result = gql_client.execute(query)


def get_acc_info():
    query = gql(account_query.format(acc_number=config.ACC_NUMBER))
    result = gql_client.execute(query)

    tariff_code = next(agreement['tariff']['tariffCode']
                       for agreement in result['account']['electricityAgreements']
                       if 'tariffCode' in agreement['tariff'])
    region_code = tariff_code[-1]
    device_id = next(device['deviceId']
                     for agreement in result['account']['electricityAgreements']
                     for meter in agreement['meterPoint']['meters']
                     for device in meter['smartDevices']
                     if 'deviceId' in device)
    curr_stdn_charge = next(agreement['tariff']['standingCharge']
                            for agreement in result['account']['electricityAgreements']
                            if 'standingCharge' in agreement['tariff'])

    if "GO" in tariff_code:
        current_tariff = "GO"
    elif "AGILE" in tariff_code:
        current_tariff = "AGILE"
    else:
        raise Exception(f"ERROR: Unknown tariff code: {tariff_code}")

    # Get consumption for today
    result = gql_client.execute(
        gql(consumption_query.format(device_id=device_id, start_date=f"{date.today()}T00:00:00Z",
                                     end_date=f"{date.today()}T23:59:59Z")))
    consumption = result['smartMeterTelemetry']

    return current_tariff, curr_stdn_charge, region_code, consumption


def get_potential_tariff_rates(tariff_short_code, region_code):
    all_products = rest_query(f"{config.BASE_URL}/products/?brand=OCTOPUS_ENERGY&is_business=false")

    # Get the required tariff from the results
    tariff_result = next((
        product for product in all_products.get('results', [])
        if product.get('display_name') == ("Agile Octopus" if tariff_short_code == "AGILE" else "Octopus Go")
           and product.get('direction') == "IMPORT"
    ), None)

    if not tariff_result:
        raise ValueError(f"Tariff not found for {tariff_short_code}")

    # Use the self links to navigate to the tariff details
    tariff_self_link = next((
        item.get('href') for item in tariff_result.get('links', [])
        if item.get('rel', '').lower() == 'self'
    ), None)

    if not tariff_self_link:
        raise ValueError(f"Self link not found for tariff {tariff_result.get('code', 'Unknown')}.")

    tariff_details = rest_query(tariff_self_link)

    # Access the standing charge including VAT
    region_tariffs = tariff_details.get('single_register_electricity_tariffs', {}).get(f'_{region_code}', {}).get('direct_debit_monthly', {})
    standing_charge_inc_vat = region_tariffs.get('standing_charge_inc_vat')

    if standing_charge_inc_vat is None:
        raise ValueError(f"Standing charge including VAT not found for region {region_code}.")

    # Find the link for standard unit rates
    links = region_tariffs.get('links', [])
    unit_rates_link = next((
        item.get('href') for item in links
        if item.get('rel', '').lower() == 'standard_unit_rates'
    ), None)

    if not unit_rates_link:
        raise ValueError(f"Standard unit rates link not found for region: {region_code}")

    # Get today's rates
    today = date.today()
    unit_rates = rest_query(
        f"{unit_rates_link}?period_from={today}T00:00:00Z&period_to={today}T23:59:59Z")

    return standing_charge_inc_vat, unit_rates.get('results', [])



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
            if rate['valid_from'] <= read_time <= rate['valid_to']
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


def get_token():
    transport = AIOHTTPTransport(url=f"{config.BASE_URL}/graphql/")
    client = Client(transport=transport, fetch_schema_from_transport=True)
    query = gql(token_query.format(api_key=config.API_KEY))
    result = client.execute(query)
    return result['obtainKrakenToken']['token']


def switch_tariff(target_tariff):
    with sync_playwright() as playwright:
        browser = None
        try:
            browser = playwright.chromium.launch(
                headless=True)
        except Exception as e:
            print(e)  # Should print out if its not working
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        page.goto("https://octopus.energy/")
        page.wait_for_timeout(1000)
        print("Octopus Energy website loaded")
        page.get_by_label("Log in to my account").click()
        page.wait_for_timeout(1000)
        page.get_by_placeholder("Email address").click()
        page.wait_for_timeout(1000)
        # replace w env
        page.get_by_placeholder("Email address").fill(config.OCTOPUS_LOGIN_EMAIL)
        page.wait_for_timeout(1000)
        page.get_by_placeholder("Email address").press("Tab")
        page.wait_for_timeout(1000)
        page.get_by_placeholder("Password").fill(config.OCTOPUS_LOGIN_PASSWD)
        page.wait_for_timeout(1000)
        page.get_by_placeholder("Password").press("Enter")
        page.wait_for_timeout(1000)
        print("Login details entered")
        # replace with env
        page.goto(f"https://octopus.energy/smart/{target_tariff.lower()}/sign-up/?accountNumber={config.ACC_NUMBER}")
        page.wait_for_timeout(10000)
        print("Tariff switch page loaded")
        page.locator("section").filter(has_text="Already have a SMETS2 or “").get_by_role("button").click()
        page.wait_for_timeout(10000)
        # check if url has success
        context.close()
        browser.close()


def verify_new_agreement():
    query = gql(account_query.format(acc_number=config.ACC_NUMBER))
    result = gql_client.execute(query)
    today = datetime.now().date()
    valid_from = next(datetime.fromisoformat(agreement['validFrom']).date()
                      for agreement in result['account']['electricityAgreements']
                      if 'validFrom' in agreement)

    # For some reason, sometimes the agreement has no end date, so I'm not sure if this bit is still relevant?
    # valid_to = datetime.fromisoformat(result['account']['electricityAgreements'][0]['validTo']).date()
    # next_year = valid_from.replace(year=valid_from.year + 1)
    return valid_from == today


def setup_gql(token):
    global gql_transport, gql_client
    gql_transport = AIOHTTPTransport(url=f"{config.BASE_URL}/graphql/", headers={'Authorization': f'{token}'})
    gql_client = Client(transport=gql_transport, fetch_schema_from_transport=True)


def compare_and_switch():
    welcome_message = "DRY RUN: " if config.DRY_RUN else ""
    welcome_message += "Octobot on. Starting comparison of today's costs..."
    send_notification(welcome_message)

    (curr_tariff, curr_stdn_charge, region_code, consumption) = get_acc_info()
    total_curr_cost = sum(float(entry['costDeltaWithTax']) for entry in consumption) + curr_stdn_charge

    (potential_std_charge, potential_unit_rates) = get_potential_tariff_rates(opposite_tariff[curr_tariff], region_code)

    potential_costs = calculate_potential_costs(consumption, potential_unit_rates)

    total_potential_calculated = sum(period['calculated_cost'] for period in potential_costs) + potential_std_charge
    summary = "Total potential cost on {}: £{:.2f} vs your current cost on {}: £{:.2f}"
    summary = summary.format(opposite_tariff[curr_tariff], total_potential_calculated / 100, curr_tariff,
                             total_curr_cost / 100)
    # 2p buffer because cba
    if (total_potential_calculated + 2) < total_curr_cost:
        switch_message = "{summary}\nInitiating Switch to {new_tariff}".format(summary=summary,
                                                                               new_tariff=opposite_tariff[curr_tariff])
        send_notification(switch_message)

        if config.DRY_RUN:
            dry_run_message = "DRY RUN: Not going through with switch today."
            send_notification(dry_run_message)
            return None

        switch_tariff(opposite_tariff[curr_tariff])
        send_notification("Tariff switch requested successfully.")
        # Give octopus some time to generate the agreement
        time.sleep(60)
        accept_new_agreement()
        send_notification("Accepted agreement. Switch successful.")

        if verify_new_agreement():
            send_notification("Verified new agreement successfully. Process finished.")
        else:
            send_notification("Unable to accept new agreement. Please check your emails.")
    else:
        send_notification("Not switching today." + summary)


def run_tariff_compare():
    try:
        setup_gql(get_token())
        if gql_transport is not None and gql_client is not None:
            compare_and_switch()
        else:
            raise Exception("ERROR: setup_gql has failed")
    except Exception:
        send_notification(traceback.format_exc())
