# Octopus Minmax Bot 🐙🤖

## Description
This bot will use your electricity usage and compare your current Smart tariff costs for the day with another smart tariff and initiate a switch if it's cheaper. See below for supported tariffs.

Due to how Octopus Energy's Smart tariffs work, switching manually makes the *new* tariff take effect from the start of the day. For example, if you switch at 11 PM, the whole day's costs will be recalculated based on your new tariff, allowing you to potentially save money by tariff-hopping.

I created this because I've been a long-time Agile customer who got tired of the price spikes. I now use this to enjoy the benefits of Agile (cheap days) without the risks (expensive days).

I personally have this running automatically every day at 11 PM inside a Raspberry Pi Docker container, but you can run it wherever you want.  It sends notifications and updates to a variety of services via [Apprise](https://github.com/caronc/apprise), but that's not required for it to work.

## How to Use

### Requirements
- An Octopus Energy Account (Get your API key [here](https://octopus.energy/dashboard/new/accounts/personal-details/api-access))
  - In case you don't have one, we both get £50 for using my referral: https://share.octopus.energy/coral-lake-50
- A smart meter
- Be on a supported Octopus Smart Tariff (see tariffs below)
- An Octopus Home Mini for real-time usage (**Important**).
  - Request one from Octopus Energy for free [here](https://octopus.energy/blog/octopus-home-mini/).

### HomeAssistant Addon

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Feelmafia%2Foctopus-minmax)

OR

To install this third-party add-on:

1. Open Home Assistant > Settings > Add-ons > Add-on Store.
2. Click the menu (three dots in the top-right corner) and select Repositories.
3. Paste the GitHub repository link into the field at the bottom:
https://github.com/eelmafia/octopus-minmax
4. Refresh the page if needed. The add-on will appear under **Octopus MinMax Bot**.

### Running Manually
1. Create a venv (`python -m venv /path/to/venv`)
2. Activate the venv (`source /path/to/venv/bin/activate`)
3. Install the Python requirements (`pip install -r requirements.txt`)
4. Optional: Configure the environment variables
5. Run `python src/main.py` from the octopus-minmax directory. If you didn't set environment variables, you can pass them to `main.py` as per the minimal example below;

```
OCTOBOT_CONFIG_PATH=./config/config.json \
WEB_PORT=5050 \
DRY_RUN=true \
ONE_OFF=true \
API_KEY=<YourAPIKey> \
ACC_NUMBER=OctopusAccountNumber> \
SWITCH_THRESHOLD=200 \
TARIFFS=go,agile \
BASE_URL=https://api.octopus.energy/v1 \
NOTIFICATION_URLS=<YourNotificationURLs> \
BATCH_NOTIFICATIONS=true \
ONLY_RESULTS_NOTIFICATIONS=false \
python3 src/main.py
```

Note: to disable the built in web server, pass NO_WEB_SERVER=true as an environment variable.

Full list of environment variables;

| Environment Variable | Description | Example |
|----------------------|-------------|---------|
| `OCTOBOT_CONFIG_PATH` | Path to the JSON config file | `./config/config.json` |
| `API_KEY` | Octopus Energy API key | `sk_live_xxxxx` |
| `ACC_NUMBER` | Octopus account number (starts with `A-`) | `A-12345678` |
| `BASE_URL` | Octopus API base URL | `https://api.octopus.energy/v1` |
| `EXECUTION_TIME` | Scheduled run time (24h `HH:MM`) | `23:00` |
| `SWITCH_THRESHOLD` | Minimum savings in pence required to switch | `200` |
| `TARIFFS` | Comma-separated tariff IDs to compare | `go,agile,flexible` |
| `ONE_OFF` | Run once and reset | `true` |
| `DRY_RUN` | Compare only; do not switch | `true` |
| `NOTIFICATION_URLS` | Comma-separated Apprise URLs | `discord://... , tgram://...` |
| `BATCH_NOTIFICATIONS` | Send notifications as a batch | `true` |
| `ONLY_RESULTS_NOTIFICATIONS` | Suppress all notifications except results | `false` |
| `WEB_USERNAME` | Web UI username (non-ingress) | `admin` |
| `WEB_PASSWORD` | Web UI password (non-ingress) | `yourpassword` |
| `WEB_PORT` | Web UI port | `5050` |
| `NO_WEB_SERVER` | Disable the web server entirely | `true` |

I recommend scheduling it to run it at 11 PM in order to leave yourself an hour as a safety margin in case Octopus takes a while to generate your new agreement.

### Running using Docker
Minimal Docker run command:

```
docker run -d \
  --name MinMaxOctopusBot \
  -p 5050:5050 \
  -v ./logs:/app/logs \
  -v ./config:/config \
  -e OCTOBOT_CONFIG_PATH=./config/config.json \
  -e WEB_PORT=5050 \
  -e DRY_RUN=true \
  -e ONE_OFF=true \
  -e API_KEY=<YourAPIKey> \
  -e ACC_NUMBER=<OctopusAccountNumber> \
  -e SWITCH_THRESHOLD=200 \
  -e TARIFFS=go,agile \
  -e BASE_URL=https://api.octopus.energy/v1 \
  -e NOTIFICATION_URLS=<YourNotificationURLs> \
  -e BATCH_NOTIFICATIONS=true \
  -e ONLY_RESULTS_NOTIFICATIONS=false \
  -e TZ=Europe/London \
  --restart unless-stopped \
  eelmafia/octopus-minmax-bot
```
or use the ```docker-compose.yaml``` file.

**Note:**

To disable the built in web server, pass NO_WEB_SERVER=true in the docker run command.

Remove the --restart unless line if you set the ONE_OFF variable or it will continuously run.

#### Using the web app
When the bot starts, a web app is launched which can be accessed via one of the following methods depending upon how you're running the bot;

* For Home Assistant, the web app is served via ingress, just click the "Open web UI" button from the addon page
* For docker users, the web app is available via the mapped port (`default: 5050`), i.e. `http://192.168.1.10:5050`
* When running manually, the web app is available either via the default port (`5050`) or whatever port you specify in the `WEB_PORT` environment variable

Note: On first run (*and always when accessing via Home Assistant*), the web app has no authentication.

Open the web app and click on the `Configuration` button

Populate the fields, paying attention to mandatory fields highlighted with an asterisk

![](https://private-user-images.githubusercontent.com/1013909/537322507-150aaa35-75cf-47fb-99ae-d72af7696f81.png?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3Njg3NjgwMDQsIm5iZiI6MTc2ODc2NzcwNCwicGF0aCI6Ii8xMDEzOTA5LzUzNzMyMjUwNy0xNTBhYWEzNS03NWNmLTQ3ZmItOTlhZS1kNzJhZjc2OTZmODEucG5nP1gtQW16LUFsZ29yaXRobT1BV1M0LUhNQUMtU0hBMjU2JlgtQW16LUNyZWRlbnRpYWw9QUtJQVZDT0RZTFNBNTNQUUs0WkElMkYyMDI2MDExOCUyRnVzLWVhc3QtMSUyRnMzJTJGYXdzNF9yZXF1ZXN0JlgtQW16LURhdGU9MjAyNjAxMThUMjAyMTQ0WiZYLUFtei1FeHBpcmVzPTMwMCZYLUFtei1TaWduYXR1cmU9YmMyNzI5YzdlMjhiZjA5NzZlZGZiMGIxZTFmOWI4NjcwMmUyMDQwZGI5ZGU5ODI5NTc2ZGQzZjk0MTFlYTBiOSZYLUFtei1TaWduZWRIZWFkZXJzPWhvc3QifQ.CISp_MzjnLGiAOjKoeKvIdNcw0qZerZdPGCpxz4FIDA)

![](https://private-user-images.githubusercontent.com/1013909/537322554-28378810-8312-4b3c-9305-0c1002c16c12.png?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3Njg3NjgwMDQsIm5iZiI6MTc2ODc2NzcwNCwicGF0aCI6Ii8xMDEzOTA5LzUzNzMyMjU1NC0yODM3ODgxMC04MzEyLTRiM2MtOTMwNS0wYzEwMDJjMTZjMTIucG5nP1gtQW16LUFsZ29yaXRobT1BV1M0LUhNQUMtU0hBMjU2JlgtQW16LUNyZWRlbnRpYWw9QUtJQVZDT0RZTFNBNTNQUUs0WkElMkYyMDI2MDExOCUyRnVzLWVhc3QtMSUyRnMzJTJGYXdzNF9yZXF1ZXN0JlgtQW16LURhdGU9MjAyNjAxMThUMjAyMTQ0WiZYLUFtei1FeHBpcmVzPTMwMCZYLUFtei1TaWduYXR1cmU9ZTExNTJlZjc3M2ZhNDliYjJkNDA3MDAyMDVmZWUxNzA0YjBkOWIzNTNjY2Q1YjZlODBmMTE3NzA2ZTlhZWMzZiZYLUFtei1TaWduZWRIZWFkZXJzPWhvc3QifQ.f9PrLXOSJ-ASs60HDi3SzAuzLYwKYe-FPv9S8Y9luH8)

Click the "Update Configuration" button to save your settings.  If you selected a One-Off Run, it will start shortly after saving the configuration.

On adding or updating the web username or password, you will (unless running in Home Assistant) be immediately prompted to login.

![](https://private-user-images.githubusercontent.com/1013909/537323069-47548396-1923-4aa0-b386-298be6692d36.png?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3Njg3NjgxMDAsIm5iZiI6MTc2ODc2NzgwMCwicGF0aCI6Ii8xMDEzOTA5LzUzNzMyMzA2OS00NzU0ODM5Ni0xOTIzLTRhYTAtYjM4Ni0yOThiZTY2OTJkMzYucG5nP1gtQW16LUFsZ29yaXRobT1BV1M0LUhNQUMtU0hBMjU2JlgtQW16LUNyZWRlbnRpYWw9QUtJQVZDT0RZTFNBNTNQUUs0WkElMkYyMDI2MDExOCUyRnVzLWVhc3QtMSUyRnMzJTJGYXdzNF9yZXF1ZXN0JlgtQW16LURhdGU9MjAyNjAxMThUMjAyMzIwWiZYLUFtei1FeHBpcmVzPTMwMCZYLUFtei1TaWduYXR1cmU9NTg5YTc5NGZhNjMxZTRhYmNiOWYwN2FlZDUzMTE0NGZkOTY3ZWM3ZTgwMDFkMGIzNzlhMTAwZmUzMjAxYWJhYSZYLUFtei1TaWduZWRIZWFkZXJzPWhvc3QifQ.m2T1nBxvM-xKOuOlez7dq_Kf-kJQoQf6USxf5hFKQTY)

The main dashboard will show you a summary of the next scheduled run.  If the bot has already run (and successfully saved the results) an additional summary box will be displayed showing the outcome of that run.

![](https://private-user-images.githubusercontent.com/1013909/537067384-c0a27a55-2ffc-4f5d-8aca-96c7ab20e9ee.png?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3Njg2MTc4ODQsIm5iZiI6MTc2ODYxNzU4NCwicGF0aCI6Ii8xMDEzOTA5LzUzNzA2NzM4NC1jMGEyN2E1NS0yZmZjLTRmNWQtOGFjYS05NmM3YWIyMGU5ZWUucG5nP1gtQW16LUFsZ29yaXRobT1BV1M0LUhNQUMtU0hBMjU2JlgtQW16LUNyZWRlbnRpYWw9QUtJQVZDT0RZTFNBNTNQUUs0WkElMkYyMDI2MDExNyUyRnVzLWVhc3QtMSUyRnMzJTJGYXdzNF9yZXF1ZXN0JlgtQW16LURhdGU9MjAyNjAxMTdUMDIzOTQ0WiZYLUFtei1FeHBpcmVzPTMwMCZYLUFtei1TaWduYXR1cmU9ZjcyOGVkY2Q1MDNlYzg0MDdhYzg5YmNjNjQ4NGU0ZGIzZjUzMjYyYTRhZjYwZGNkMTllNGZkY2QwYzMyOGI4OSZYLUFtei1TaWduZWRIZWFkZXJzPWhvc3QifQ.9krH_FqoARFkbvPmV_evdFnI4ODX7uIaHKQtMpgvskc)

The logs page allows you to view the logs generated by the bot.  You can configure the auto refresh frequency and which level of logs you want to see.

![](https://private-user-images.githubusercontent.com/1013909/537070174-71c5ffef-38fb-43e6-aba1-4336c3fd2018.png?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3Njg3NjgxMDAsIm5iZiI6MTc2ODc2NzgwMCwicGF0aCI6Ii8xMDEzOTA5LzUzNzA3MDE3NC03MWM1ZmZlZi0zOGZiLTQzZTYtYWJhMS00MzM2YzNmZDIwMTgucG5nP1gtQW16LUFsZ29yaXRobT1BV1M0LUhNQUMtU0hBMjU2JlgtQW16LUNyZWRlbnRpYWw9QUtJQVZDT0RZTFNBNTNQUUs0WkElMkYyMDI2MDExOCUyRnVzLWVhc3QtMSUyRnMzJTJGYXdzNF9yZXF1ZXN0JlgtQW16LURhdGU9MjAyNjAxMThUMjAyMzIwWiZYLUFtei1FeHBpcmVzPTMwMCZYLUFtei1TaWduYXR1cmU9NWQ4MDA1Mjg2YTYyNzFmMWI1NTg3NDNmZDRkMDU4ZTJjZTVjOWI5MTVlMzFmNTMyMDE2NDZhN2U5Yjg0MDY0ZCZYLUFtei1TaWduZWRIZWFkZXJzPWhvc3QifQ.ZuMU_3vNk06nFCXvrLb0KISQpF-QrhBlldVXJecYJq8)

#### Supported Tariffs

Below is a list of supported tariffs, their IDs (to use in environment variables), and whether they are switchable.

**None switchable tariffs are use for PRICE COMPARISON ONLY**

| Tariff Name      | Tariff ID | Switchable |
|------------------|-----------|------------|
| Flexible Octopus | flexible  | ❌          |
| Agile Octopus    | agile     | ✅          |
| Cosy Octopus     | cosy      | ✅          |
| Octopus Go       | go        | ✅          |


#### Setting up Apprise Notifications

The `NOTIFICATION_URLS` environment variable and the `Notification URLs (Apprise)` field in the web app allows you to configure notifications using the powerful [Apprise](https://github.com/caronc/apprise) library.  Apprise supports a wide variety of notification services, including Discord, Telegram, Slack, email, and many more.

To configure notifications:

1.  **Determine your desired notification services:**  Decide which services you want to receive notifications on (e.g., Discord, Telegram).

2.  **Find the Apprise URL format for each service:**  Consult the [Apprise documentation](https://github.com/caronc/apprise/wiki) to find the correct URL format for each service you've chosen.  For example:

    *   **Discord:** `discord://webhook_id/webhook_token`
    *   **Telegram:** `tgram://bottoken/ChatID`

3.  **Set the `NOTIFICATION_URLS` environment variable or the `Notification URLs (Apprise)` field in the web app:** Create a comma-separated string containing the Apprise URLs for all your desired services.  For example:

    ```
    NOTIFICATION_URLS="discord://webhook_id/webhook_token,tgram://bottoken/ChatID,mailto://user:pass@example.com?to=recipient@example.com"
    ```
as an environment variable or;

	```
	discord://webhook_id/webhook_token,tgram://bottoken/ChatID,mailto://user:pass@example.com?to=recipient@example.com
	```
in the web app.

	**Make sure to replace the example values with your actual credentials!**
