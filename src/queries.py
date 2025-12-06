token_query = """mutation {{
	obtainKrakenToken(input: {{ APIKey: "{api_key}" }}) {{
	    token
	}}
}}"""

accept_terms_query = """mutation {{
    acceptTermsAndConditions(input: {{
        accountNumber: "{account_number}",
        enrolmentId: "{enrolment_id}",
        termsVersion: {{
            versionMajor: {version_major},
            versionMinor: {version_minor}
        }}
    }})
    {{
    acceptedVersion
  }}
}}"""

get_terms_version_query = """query {{
    termsAndConditionsForProduct(productCode: "{product_code}") {{
        name
        version
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
            direction
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

switch_query = """mutation {{
  startOnboardingProcess(input: {{
    accountNumber: "{account_number}",
    mpan: "{mpan}",
    productCode: "{product_code}",
    targetAgreementChangeDate: "{change_date}"
  }})
  {{
    onboardingProcess {{
      id
    }}
    productEnrolment {{
      id
    }}
  }}
}}"""