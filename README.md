# Octopus Minmax Bot 🐙🤖

## Description
This bot will use your electricity usage and compare your current Smart tariff costs for the day with another smart tariff and initiate a switch if it's cheaper. Currently, it switches only between Octopus Agile and Octopus Go.

Due to how Octopus Energy's Smart tariffs work, switching manually makes the *new* tariff take effect from the start of the day. For example, if you switch at 11 PM, the whole day's costs will be recalculated based on your new tariff, allowing you to potentially save money by tariff-hopping.

I created this because I've been a long-time Agile customer who got tired of the price spikes. I now use this to enjoy the benefits of Agile (cheap days) without the risks (expensive days).

I personally have this running automatically every day at 11 PM inside a Raspberry Pi Docker container, but you can run it wherever you want.  It sends notifications and updates to a variety of services via [Apprise](https://github.com/caronc/apprise), but that's not required for it to work.

## How to Use

### Requirements
- An Octopus Energy Account  
  - In case you don't have one, we both get £50 for using my referral: https://share.octopus.energy/coral-lake-50
  - Get your API key [here](https://octopus.energy/dashboard/new/accounts/personal-details/api-access)
- A smart meter
- Be on Octopus Agile or Octopus Go (More options can be added in the future)
- An Octopus Home Mini for real-time usage (**Important**). Get one for free [here](https://octopus.energy/blog/octopus-home-mini/).

### Running Manually
1. Install the Python requirements.
2. Configure the environment variables.
3. Schedule this to run once a day with a CRON job or Docker. I recommend running it at 11 PM to leave yourself an hour as a safety margin in case Octopus takes a while to generate your new agreement.

### Running using Docker
Docker run command:
```
docker run -d \
  --name MinMaxOctopusBot \
  -e ACC_NUMBER="<your_account_number>" \
  -e API_KEY="<your_api_key>" \
  -e EXECUTION_TIME="23:00" \
  -e NOTIFICATION_URLS="<apprise_notification_urls>" \
  -e ONE_OFF=false \
  -e DRY_RUN=false \
  -e PYTHONUNBUFFERED=1 \
  -e TARIFFS=go,agile,flexible \
  --restart unless-stopped \
  eelmafia/octopus-minmax-bot
```
or use the docker-compose.yaml **Don't forget to add your environment variables**

Note : Remove the --restart unless line if you set the ONE_OFF variable or it will continuously run.

#### Environment Variables
| Variable               | Description                                                                                                                                                                                                             |
|------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `ACC_NUMBER`           | Your Octopus Energy account number.                                                                                                                                                                                     |
| `API_KEY`              | API token for accessing your Octopus Energy account.                                                                                                                                                                    |
| `TARIFFS`              | A list of tariffs to compare against. Default is go,agile,flexible                                                                                                                                                      | 
| `EXECUTION_TIME`       | (Optional) The time (HH:MM) when the script should execute. Default is `23:00` (11 PM).                                                                                                                                 |
| `NOTIFICATION_URLS`    | (Optional) A comma-separated list of [Apprise](https://github.com/caronc/apprise) notification URLs for sending logs and updates.  See [Apprise documentation](https://github.com/caronc/apprise/wiki) for URL formats. |
| `ONE_OFF`              | (Optional) A flag for you to simply trigger an immediate execution instead of starting scheduling.                                                                                                                      |
| `DRY_RUN`              | (optional) A flag to compare but not switch tariffs.                                                                                                                                                                    |

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

The `NOTIFICATION_URLS` environment variable allows you to configure notifications using the powerful [Apprise](https://github.com/caronc/apprise) library.  Apprise supports a wide variety of notification services, including Discord, Telegram, Slack, email, and many more.

To configure notifications:

1.  **Determine your desired notification services:**  Decide which services you want to receive notifications on (e.g., Discord, Telegram).

2.  **Find the Apprise URL format for each service:**  Consult the [Apprise documentation](https://github.com/caronc/apprise/wiki) to find the correct URL format for each service you've chosen.  For example:

    *   **Discord:** `discord://webhook_id/webhook_token`
    *   **Telegram:** `tgram://bottoken/ChatID`

3.  **Set the `NOTIFICATION_URLS` environment variable:** Create a comma-separated string containing the Apprise URLs for all your desired services.  For example:

    ```bash
    NOTIFICATION_URLS="discord://webhook_id/webhook_token,tgram://bottoken/ChatID,mailto://user:pass@example.com?to=recipient@example.com"
    ```

    Make sure to replace the example values with your actual credentials.

4.  **Restart the container (if using Docker) or run the script:**  The bot will now send notifications to all the configured services.
