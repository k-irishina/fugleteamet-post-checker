# Fugleteamet bird alert 🐦

Sends a Telegram bot message whenever a new bird is posted for adoption on
https://www.fugleteamet.no/adopsjon. It checks every 20 minutes between 08:00 and 21:00 Oslo time..
  Made for myself to avoid checking the site all the time.

## Tech

Uses python with minimal dependencies and executes as a simple script. GitHub Actions runs act as the scheduler and execute the checking.

## How to get alerts

1. In Telegram, find the bot **@fugleteamet_post_bot** and press **Start**.
2. Send it the message: **please add me**
3. Please notify me once you've done this. Once you've been added to the list, you'll get a message with a photo and link
   every time a new bird is posted.

To stop getting alerts, block the bot or ask me to remove you.

---

## For the maintainer: adding someone

1. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser (or run
   `TELEGRAM_TOKEN=... python3 bot.py chatid`) and find their `"chat":{"id":...}` next to "please add me".
   Messages only stay there for about 24 hours.

2.  Add the token to the variable in GitHub actions.
