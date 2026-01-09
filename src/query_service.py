import requests
from queries import *
import time
import logging

logger = logging.getLogger('octobot.query_service')
MAX_RETRIES = 5
BASE_WAIT_BEFORE_RETRY_SECONDS = 30

class QueryService:
    _shared_token = None
    def __init__(self, api_key: str, base_url: str):
        logger.debug(f"Initialising {__class__.__name__}")
        self.base_url = base_url
        self.api_key = api_key
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/605.1.15 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/605.1.15',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/json'
        }
        self.graphql_endpoint = f"{self.base_url}/graphql/"

        if QueryService._shared_token is None:
            QueryService._shared_token = self._get_token()


    def _get_token(self):
        logger.debug("Getting token")
        formatted_token_query = token_query.format(api_key=self.api_key)
        headers = self.headers.copy()
        payload = {"query": formatted_token_query, "variables": {}}

        try:
            response = requests.post(
                self.graphql_endpoint,
                headers=headers,
                json=payload,
                timeout=60
            )

            response.raise_for_status()
            result = response.json()
            logger.debug(f"GQL query response: status={response.status_code} | body={result}")

            if "errors" in result:
                raise Exception(f"GQL errors: {result['errors']}")

            token = result.get("data", {}).get("obtainKrakenToken", {}).get("token")

            if not token:
                raise Exception("GQL token missing from response")

            logger.info(f"Acquired token: {token[:20]}...")
            return token
        except Exception as e:
            logger.error(f"Failed to get token: {type(e).__name__} - {e}")
            raise Exception("Failed to get token")

    def execute_gql_query(self, query: str):
        logger.debug(f"Executing GQL query: '{query}'")
        retry = 0
        token_refreshed = False
        while retry < MAX_RETRIES:
            headers = self.headers.copy()

            if self._shared_token:
                headers["Authorization"] = self._shared_token

            payload = {
                "query": query,
                "variables": {}
            }
            try:
                response = requests.post(
                    self.graphql_endpoint,
                    headers=headers,
                    json=payload,
                    timeout=60
                )

                logger.debug(f"GQL query response: status={response.status_code} | body={response.json()}")
                if response.ok:
                    result = response.json()
                    if "errors" in result:
                        error_codes = [e.get("extensions", {}).get("errorCode") for e in result.get("errors", [])]
                        if "KT-CT-1124" in error_codes and not token_refreshed:
                            logger.debug("JWT expired, refreshing token...")
                            try:
                                QueryService._shared_token = self._get_token()
                                token_refreshed = True
                                continue  # Retry with new token
                            except Exception as e:
                                logger.warning(f"Failed to refresh token: {e}")
                        raise Exception(f"GQL errors: {result['errors']}")

                    data = result.get("data")
                    if data and isinstance(data, dict) and len(data) > 0:
                        return data
                    else:
                        raise Exception("No 'data' returned from GraphQL query")

                if response.status_code in [401, 403] and not token_refreshed:
                    logger.debug("Authentication failed, refreshing token...")
                    try:
                        QueryService._shared_token = self._get_token()
                        token_refreshed = True
                        continue

                    except Exception as e:
                        logger.warning(f"Failed to refresh token: {e}")

            except Exception as e:
                logger.warning(f"Request exception on attempt {retry + 1}/{MAX_RETRIES}: {type(e).__name__} - {e}")
                if retry == MAX_RETRIES - 1:
                    raise Exception(f"GQL query failed after {MAX_RETRIES} attempts: {e}")

            if retry == MAX_RETRIES - 1:
                logger.warning(f"GQL query failed after {MAX_RETRIES} attempts: {response.status_code}: {response.text}")
                raise Exception(f"GQL query failed after {MAX_RETRIES} attempts: {response.status_code}: {response.text}")


            # Calculate wait time with exponential backoff
            wait_time = BASE_WAIT_BEFORE_RETRY_SECONDS * (2 ** retry)
            logger.debug(f"Request failed with status {response.status_code}. Retrying in {wait_time} seconds... (attempt {retry + 1}/{MAX_RETRIES})")
            retry += 1
            time.sleep(wait_time)

    def execute_rest_query(self, url: str):
        logger.info(f"Executing REST query: {url}")
        try:
            response = requests.get(url, timeout=60)
            logger.debug(f"REST query response: status={response.status_code} | body={response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text[:200]}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.exception(f"Request failed for {url}: {type(e).__name__} - {e}")
            raise Exception(f"ERROR: Request failed for {url}: {type(e).__name__} - {e}")

