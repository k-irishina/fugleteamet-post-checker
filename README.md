# Fugleteamet bird alert 🐦

Sends a Telegram bot message whenever a new bird is posted for adoption on
https://www.fugleteamet.no/adopsjon. It checks twice a day, around 11:00 and 18:00 Oslo time (Github action scheduler is notoriously off-time).
  Made for myself to avoid checking the site all the time.

## Tech

Uses python with minimal dependencies and executes as a simple script. GitHub Actions runs act as the scheduler and execute the checking. Using Actions cache to store the reference bird list.

## How to get alerts

1. In Telegram, find the bot **@fugleteamet_post_bot** and press **Start**.
2. Send it the message: **please add me**
3. You're added automatically within about 12 hours. The bot then sends you a
   "✅ You're now following…" message. After that, you'll get a message with a photo and link
   every time a new bird is posted.

To stop getting alerts, block the bot or ask me to remove you.

---
