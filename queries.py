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