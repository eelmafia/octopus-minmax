# Octopus Minmax Bot 🐙🤖

## Description
This bot will use your electricity usage and compare your current Smart tariff costs for the day with another smart tariff and initiate a switch if it's cheaper. See below for supported tariffs.

Due to how Octopus Energy's Smart tariffs work, switching manually makes the *new* tariff take effect from the start of the day. For example, if you switch at 11 PM, the whole day's costs will be recalculated based on your new tariff, allowing you to potentially save money by tariff-hopping.

I created this because I've been a long-time Agile customer who got tired of the price spikes. I now use this to enjoy the benefits of Agile (cheap days) without the risks (expensive days).

I personally have this running automatically every day at 11 PM inside a Raspberry Pi Docker container, but you can run it wherever you want.  It sends notifications and updates to a variety of services via [Apprise](https://github.com/caronc/apprise), but that's not required for it to work.

### Operating Modes

The bot supports two operating modes:

1. **Retrospective Mode (Default)**: Compares tariffs based on actual usage from the current day and switches if a better tariff is found. This is the traditional mode that looks back at what you've already used.

2. **Predictive Mode**: Designed for battery optimization, this mode looks ahead at tomorrow's rates and makes a decision in advance. It's ideal for users with battery storage systems who want to optimise charging based on predicted rates. The bot makes a decision at a specified time (default 17:00) and executes the switch at midnight (default 00:01).

## How to Use

### Requirements
- An Octopus Energy Account  
  - In case you don't have one, we both get £50 for using my referral: https://share.octopus.energy/coral-lake-50
  - Get your API key [here](https://octopus.energy/dashboard/new/accounts/personal-details/api-access)
- A smart meter
- Be on a supported Octopus Smart Tariff (see tariffs below)
- An Octopus Home Mini for real-time usage (**Important**). Get one for free [here](https://octopus.energy/blog/octopus-home-mini/).

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
1. Install the Python requirements.
2. Configure the environment variables.
3. Schedule this to run once a day with a CRON job or Docker. I recommend running it at 11 PM to leave yourself an hour as a safety margin in case Octopus takes a while to generate your new agreement.

### Running using Docker

#### Retrospective Mode (Default)
Standard Docker run command for retrospective mode:
```
docker run -d \
  --name MinMaxOctopusBot \
  -e ACC_NUMBER="<your_account_number>" \
  -e API_KEY="<your_api_key>" \
  -e EXECUTION_TIME="23:00" \
  -e SWITCH_THRESHOLD=2 \
  -e NOTIFICATION_URLS="<apprise_notification_urls>" \
  -e ONE_OFF=false \
  -e DRY_RUN=false \
  -e TARIFFS=go,agile,flexible \
  -e TZ=Europe/London \
  -e BATCH_NOTIFICATIONS=false \
  --restart unless-stopped \
  eelmafia/octopus-minmax-bot
```

#### Predictive Mode
Docker run command for predictive mode (battery optimization):
```
docker run -d \
  --name MinMaxOctopusBot \
  -e ACC_NUMBER="<your_account_number>" \
  -e API_KEY="<your_api_key>" \
  -e PREDICTIVE_MODE=true \
  -e DECISION_TIME="17:00" \
  -e SWITCH_TIME="00:01" \
  -e TARIFFS=go,agile \
  -e BATTERY_CAPACITY_KWH=9.5 \
  -e BATTERY_CHARGE_RATE_KW=3.6 \
  -e BATTERY_MIN_CHARGE_PERCENT=0.8 \
  -e CHEAP_RATE_MULTIPLIER=1.2 \
  -e NOTIFICATION_URLS="<apprise_notification_urls>" \
  -e TZ=Europe/London \
  --restart unless-stopped \
  eelmafia/octopus-minmax-bot
```

**Note:** Remove the `--restart unless-stopped` line if you set the `ONE_OFF` variable to `true`, or it will continuously run. You can also use the `docker-compose.yaml` file - **don't forget to add your environment variables**.

#### Environment Variables

##### Core Configuration
| Variable                    | Description                                                                                                                                                                                                             |
|-----------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `ACC_NUMBER`                | Your Octopus Energy account number.                                                                                                                                                                                     |
| `API_KEY`                   | API token for accessing your Octopus Energy account.                                                                                                                                                                    |
| `TARIFFS`                   | A list of tariffs to compare against. Default is `go,agile,flexible`                                                                                                                                                      | 
| `EXECUTION_TIME`            | (Optional) The time (HH:MM) when the script should execute in retrospective mode. Default is `23:00` (11 PM). **Note:** This is ignored when `PREDICTIVE_MODE=true`. |
| `SWITCH_THRESHOLD`          | A value (in pence) which the saving must be before the switch occurs. Default is `2` (2p). **Note:** This is only used in retrospective mode. |
| `NOTIFICATION_URLS`         | (Optional) A comma-separated list of [Apprise](https://github.com/caronc/apprise) notification URLs for sending logs and updates.  See [Apprise documentation](https://github.com/caronc/apprise/wiki) for URL formats. |
| `ONE_OFF`                   | (Optional) A flag for you to simply trigger an immediate execution instead of starting scheduling. Set to `true` to run once and exit.                                                                                                                      |
| `DRY_RUN`                   | (Optional) A flag to compare but not switch tariffs. Set to `true` to test without making actual switches.                                                                                                                                                                    |
| `BATCH_NOTIFICATIONS`       | (Optional) A flag to send messages in one batch rather than individually. Set to `true` to batch notifications.                                                                                                                                               |
| `DEBUG`                     | (Optional) Enable debug mode for detailed logging. Set to `true` to enable. Default is `false`. |

##### Predictive Mode Configuration
| Variable                    | Description                                                                                                                                                                                                             |
|-----------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `PREDICTIVE_MODE`           | (Optional) Enable predictive mode for battery optimization. Set to `true` to enable. Default is `false`. When enabled, the bot checks tomorrow's rates and makes decisions in advance. |
| `DECISION_TIME`              | (Optional) The time (HH:MM) when the bot makes a decision about tomorrow's tariff in predictive mode. Default is `17:00` (5 PM). |
| `SWITCH_TIME`               | (Optional) The time (HH:MM) when the switch is executed in predictive mode. Default is `00:01` (12:01 AM). |
| `BATTERY_CAPACITY_KWH`      | (Optional) Battery capacity in kWh for predictive mode calculations. Default is `9.5`. |
| `BATTERY_CHARGE_RATE_KW`    | (Optional) Battery charge rate in kW for predictive mode calculations. Default is `3.6`. |
| `BATTERY_MIN_CHARGE_PERCENT`| (Optional) Minimum charge percentage to count as a viable charging period. Default is `0.8` (80%). |
| `CHEAP_RATE_MULTIPLIER`     | (Optional) Multiplier for Go rate to determine "cheap" periods (e.g., 1.2 = 120% of Go rate). Default is `1.2`. |

#### Supported Tariffs

Below is a list of supported tariffs, their IDs (to use in environment variables), and whether they are switchable.

**None switchable tariffs are use for PRICE COMPARISON ONLY**

| Tariff Name      | Tariff ID | Switchable |
|------------------|-----------|------------|
| Flexible Octopus | flexible  | ❌          |
| Agile Octopus    | agile     | ✅          |
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

## Predictive Mode

Predictive mode is designed for users with battery storage systems who want to automatically switch between tariffs based on predicted rates for the next day. This mode works in two phases and is best paired with battery management systems like [predbat](https://github.com/springfall2008/batpred) that can optimise charging schedules once the tariff has been switched.

### Why Use Predictive Mode?

If you have a battery storage system, you can benefit from switching between tariffs to optimise your charging costs:

- **Octopus Go** offers a cheap overnight rate (typically 00:30-05:30) perfect for charging your battery when rates are low
- **Agile Octopus** offers dynamic rates that can sometimes be cheaper than Go's overnight rate during the day

Predictive mode automatically selects the best tariff for tomorrow based on predicted rates, ensuring you're on the optimal tariff before the day begins. This is particularly useful because:

1. Tariff switches take effect from the start of the day, so you need to decide in advance
2. Tomorrow's rates are typically available from around 4 PM onwards
3. You want the switch to happen at midnight so the new tariff is active for the entire day

### How Predictive Mode Works

Predictive mode operates in two distinct phases:

#### Phase 1: Decision Phase (Default: 17:00)

At the decision time (typically 17:00), the bot:

1. **Fetches Tomorrow's Rates**: Retrieves predicted rates for Agile Octopus and Octopus Go for the next day from the Octopus Energy API
2. **Fetches Go Overnight Rate**: Automatically retrieves the Octopus Go overnight rate from the API (no manual configuration needed)
3. **Analyses Charging Opportunities**: 
   - Compares Agile rates against Go's overnight rate
   - Identifies periods where Agile rates are at or below a threshold (default: 120% of Go's rate)
   - Considers your battery capacity and charge rate to determine viable charging windows
4. **Makes a Decision**: Chooses the best tariff based on:
   - Number of cheap periods available on Agile
   - Whether Agile rates are cheaper than Go's overnight rate
   - Battery charging requirements (capacity, charge rate, minimum charge percentage)
5. **Stores the Decision**: Saves the decision to be executed later

If tomorrow's rates aren't available yet, the bot will automatically retry every hour until 23:00.

#### Phase 2: Switch Phase (Default: 00:01)

At the switch time (typically 00:01), the bot:

1. **Loads the Stored Decision**: Retrieves the decision made earlier
2. **Validates the Decision**: Ensures the decision is for today's date
3. **Executes the Switch**: Initiates the tariff switch through the Octopus Energy API
4. **Accepts the Agreement**: Automatically accepts the new tariff agreement

The switch happens at midnight to ensure the new tariff is active for the entire day.

### Integration with predbat

Predictive mode is designed to work seamlessly with [predbat](https://github.com/springfall2008/batpred), a battery prediction and optimisation system. Here's how they work together:

1. **Octopus MinMax Bot (This Bot)**: 
   - Runs at 17:00 to check tomorrow's rates
   - Makes a decision about which tariff will be best
   - Switches your tariff at midnight

2. **predbat**:
   - Runs after the tariff switch (typically in the early morning)
   - Fetches the actual rates for your new tariff from the Octopus API
   - Creates an optimised charging plan based on:
     - Your actual tariff rates (now that you've switched)
     - Predicted electricity usage
     - Predicted solar generation
     - Battery capacity and efficiency
   - Controls your battery to charge at the optimal times

This two-step approach ensures you're always on the best tariff, and then predbat optimises your battery usage within that tariff.

### Predictive Mode Example

For a typical setup with a 9.5 kWh battery and 3.6 kW charge rate:

```bash
docker run -d \
  --name MinMaxOctopusBot \
  -e ACC_NUMBER="A-XXXXXXXX" \
  -e API_KEY="sk_live_..." \
  -e PREDICTIVE_MODE=true \
  -e DECISION_TIME="17:00" \
  -e SWITCH_TIME="00:01" \
  -e TARIFFS=go,agile \
  -e BATTERY_CAPACITY_KWH=9.5 \
  -e BATTERY_CHARGE_RATE_KW=3.6 \
  -e BATTERY_MIN_CHARGE_PERCENT=0.8 \
  -e CHEAP_RATE_MULTIPLIER=1.2 \
  -e TZ=Europe/London \
  --restart unless-stopped \
  eelmafia/octopus-minmax-bot
```

### Testing Predictive Mode

You can test predictive mode with a one-off run to see what decision it would make:

```bash
docker run --rm \
  -e ACC_NUMBER="A-XXXXXXXX" \
  -e API_KEY="sk_live_..." \
  -e PREDICTIVE_MODE=true \
  -e ONE_OFF=true \
  -e DRY_RUN=true \
  -e TARIFFS=go,agile \
  -e DEBUG=true \
  eelmafia/octopus-minmax-bot \
  python -u test_predictive.py
```

This will make a decision without actually switching, allowing you to see what the bot would choose based on tomorrow's predicted rates.
