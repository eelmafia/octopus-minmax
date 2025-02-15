# Octopus Minmax Bot 🐙🤖

## Description
This bot will use your electricity usage and compare your current Smart tariff costs for the day with another smart tariff and initiate a switch if it's cheaper. Currently, it switches only between Octopus Agile and Octopus Go.

Due to how Octopus Energy's Smart tariffs work, switching manually makes the *new* tariff take effect from the start of the day. For example, if you switch at 11 PM, the whole day's costs will be recalculated based on your new tariff, allowing you to potentially save money by tariff-hopping.

I created this because I've been a long-time Agile customer who got tired of the price spikes. I now use this to enjoy the benefits of Agile (cheap days) without the risks (expensive days).

I personally have this running automatically every day at 11 PM inside a Raspberry Pi Docker container, but you can run it wherever you want. It also uses Discord webhooks to send you updates and logs, but that's not necessary for it to work.

## How to Use
**Note**: This requires your email and password when using Playwright to log into your account. None of your data goes anywhere except to Octopus Energy.

### Requirements
- An Octopus Energy Account  
  - In case you don't have one, we both get £50 for using my referral: https://share.octopus.energy/coral-lake-50
  - Get your API key [here](https://octopus.energy/dashboard/new/accounts/personal-details/api-access)
- A smart meter
- Be on Octopus Agile or Octopus Go (More options can be added in the future)
- An Octopus Home Mini for real-time usage (**Important**)

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
  -e OCTOPUS_LOGIN_EMAIL="<your_email>" \
  -e OCTOPUS_LOGIN_PASSWD="<your_password>" \
  -e EXECUTION_TIME="23:00" \
  -e DISCORD_WEBHOOK="<your_webhook_url>" \
  -e ONE_OFF=false \
  -e DRY_RUN=false \
  -e PYTHONUNBUFFERED=1 \
  --restart unless-stopped \
  eelmafia/octopus-minmax-bot
```

or use the docker-compose.yaml **Don't forget to add your environment variables**

#### Environment Variables
| Variable               | Description                                                                                                                                                                               |
|------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `ACC_NUMBER`           | Your Octopus Energy account number.                                                                                                                                                       |
| `API_KEY`              | API token for accessing your Octopus Energy account.                                                                                                                                      |
| `OCTOPUS_LOGIN_EMAIL`  | The email associated with your Octopus Energy account.                                                                                                                                    |
| `OCTOPUS_LOGIN_PASSWD` | The password for your Octopus Energy account.                                                                                                                                             |
| `EXECUTION_TIME`       | (Optional) The time (HH:MM) when the script should execute. Default is `23:00` (11 PM).                                                                                                   |
| `DISCORD_WEBHOOK`      | (Optional) A Discord webhook URL for sending logs and updates.                                                                                                                            |
| `TELEGRAM_BOT_TOKEN`   | (Optional) The Telegram Bot token. Create a bot via [BotFather](https://core.telegram.org/bots#6-botfather)                                                                               |
| `TELEGRAM_CHAT_ID`     | (Optional) The Telegram Chat ID. You can obtain the chat ID using the method mentioned in [this guide](https://stackoverflow.com/questions/32423837/telegram-bot-how-to-get-the-chat-id). |
| `ONE_OFF`              | (Optional) A flag for you to simply trigger an immediate execution instead of starting scheduling                                                                                         |
