#!/usr/bin/env python3
"""Watches https://www.fugleteamet.no/adopsjon and sends new listings to Telegram.

Env:
  TELEGRAM_TOKEN    bot token from @BotFather (required)
  TELEGRAM_CHAT_ID  comma-separated chat ids of receivers (run `python3 bot.py chatid` to find them).
                    Everyone gets new birds; only the first id gets error/status messages.
  CHECK_INTERVAL    seconds between checks (default 1200 = 20 min)
  STATE_FILE        where seen listings are stored (default ./seen.json)

"""
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://www.fugleteamet.no"
PAGE = BASE + "/adopsjon"
TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_IDS = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
ADMIN_CHAT_ID = CHAT_IDS[0] if CHAT_IDS else ""
INTERVAL = int(os.environ.get("CHECK_INTERVAL", "1200"))
STATE_FILE = os.environ.get("STATE_FILE", "seen.json")

CARD_RE = re.compile(r'<div class="listing-card".*?Se hele annonsen</a>', re.S)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (fugleteamet-watcher)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse_listings(page):
    listings = {}
    for card in CARD_RE.findall(page):
        href = re.search(r'href="(/annonse/[^"]+)"', card)
        if not href:
            continue
        title = re.search(r"<h3[^>]*>(.*?)</h3>", card, re.S)
        excerpt = re.search(r'listing-content__excerpt[^>]*>(.*?)</p>', card, re.S)
        img = re.search(r'<img src="([^"]+)"', card)
        listings[href.group(1)] = {
            "title": html.unescape(title.group(1).strip()) if title else href.group(1),
            "excerpt": html.unescape(excerpt.group(1).strip()) if excerpt else "",
            "image": html.unescape(img.group(1)) if img else None,
            "url": BASE + href.group(1),
        }
    return listings


def telegram_sender(method, **params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{TOKEN}/{method}", data, timeout=30) as r:
        return json.load(r)


def notify(item):
    caption = f"🐦 New bird for adoption: <b>{html.escape(item['title'])}</b>\n\n{html.escape(item['excerpt'][:700])}\n\n{item['url']}"
    for chat_id in CHAT_IDS:
        # One receiver failing (e.g. they blocked the bot) must not stop the others.
        try:
            if item["image"]:
                try:
                    telegram_sender("sendPhoto", chat_id=chat_id, photo=item["image"], caption=caption[:1024], parse_mode="HTML")
                    continue
                except Exception as e:
                    print("sendPhoto failed, falling back to text:", e, flush=True)
            telegram_sender("sendMessage", chat_id=chat_id, text=caption, parse_mode="HTML")
        except Exception as e:
            print(f"could not notify {chat_id}:", e, flush=True)


def load_state():
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except FileNotFoundError:
        return {"seen": None, "failing": False}
    if isinstance(state, list):
        state = {"seen": state}
    return {"seen": state.get("seen"), "failing": state.get("failing", False)}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump({"seen": sorted(state["seen"] or []), "failing": state["failing"]}, f, indent=1)


def check_new_posts(state):
    listings = parse_listings(fetch(PAGE))
    if not listings:
        raise RuntimeError("found 0 listings - page layout may have changed")
    if state["seen"] is None:
        # First run: remember what's there now
        state["seen"] = list(listings)
        save_state(state)
        telegram_sender("sendMessage", chat_id=ADMIN_CHAT_ID,
           text=f"✅ Following {PAGE} ({len(listings)} listings). You will get notifications when new ones appear.")
        print(f"initialized with {len(listings)} listings", flush=True)
        return
    seen = set(state["seen"])
    new = [k for k in listings if k not in seen]
    for k in new:
        notify(listings[k])
        seen.add(k)
        state["seen"] = seen
        save_state(state)  # save after each send so a crash doesn't re-send
    print(f"{time.strftime('%F %T')} checked: {len(listings)} listings, {len(new)} new", flush=True)


def run_check_once():
    state = load_state()
    try:
        check_new_posts(state)
        if state["failing"]:
            state["failing"] = False
            telegram_sender("sendMessage", chat_id=ADMIN_CHAT_ID, text="✅ Fugleteamet-check works again.")
    except Exception as e:
        print("check failed:", e, flush=True)
        if not state["failing"]:  # alert once per outage, not every run
            try:
                telegram_sender("sendMessage", chat_id=ADMIN_CHAT_ID, text=f"⚠️ Fugleteamet-check failed:\n{e}")
                state["failing"] = True
            except Exception as e2:
                print("could not send error alert:", e2, flush=True)
    save_state(state)


def print_chat_id():
    updates = telegram_sender("getUpdates").get("result", [])
    msgs = [u["message"] for u in updates if "message" in u]
    if not msgs:
        print("No messages yet - send any message to your bot in Telegram, then run this again.")
    for m in msgs:
        chat = m["chat"]
        name = " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")]))
        user = f" @{chat['username']}" if chat.get("username") else ""
        print(f"{chat['id']}  {name}{user}: {m.get('text', '')!r}")


def main():
    if not TOKEN:
        sys.exit("Set TELEGRAM_TOKEN")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "loop"
    if cmd == "chatid":
        return print_chat_id()
    if not CHAT_IDS:
        sys.exit("Set TELEGRAM_CHAT_ID (run `python3 bot.py chatid` to find it)")
    if cmd == "once":
        return run_check_once()
    while True:
        run_check_once()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
