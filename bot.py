#!/usr/bin/env python3
"""Watches https://www.fugleteamet.no/adopsjon and sends new listings to Telegram.

Env:
  TELEGRAM_TOKEN    bot token from @BotFather
  TELEGRAM_CHAT_ID  comma-separated chat ids of receivers (run `python3 bot.py chatid` to find them).
                    Everyone gets new birds; only the first id gets error/status messages.
  GH_PAT             lets subscribers.yml update TELEGRAM_CHAT_ID

"""
import hashlib
import hmac
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
INTERVAL = 1200
STATE_FILE = "seen.json"
CHAT_IDS_OUT = "chat_ids.txt"
IN_GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"

ADD_ME_RE = re.compile(r"\badd me\b", re.I)

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
        return {"seen": None, "failing": False, "welcomed": None}
    if isinstance(state, list):
        state = {"seen": state}
    welcomed = state.get("welcomed")
    if welcomed is not None:  # older state files stored plain chat ids
        welcomed = [id_hash(c) if re.fullmatch(r"-?\d+", c) else c for c in welcomed]
    return {"seen": state.get("seen"), "failing": state.get("failing", False), "welcomed": welcomed}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump({"seen": sorted(state["seen"] or []), "failing": state["failing"],
                   "welcomed": sorted(state["welcomed"] or [])}, f, indent=1)


def id_hash(chat_id):
    """Keyed with the bot token hash of a chat id, so we don't store plain chat ids"""
    return hmac.new(TOKEN.encode(), chat_id.encode(), hashlib.sha256).hexdigest()[:32]


def welcome_new_receivers(state):
    """Send a one-time message to receivers that haven't had one yet to let them know the bot works."""
    current = {id_hash(c) for c in CHAT_IDS}
    if state["seen"] is None:
        state["welcomed"] = list(current)
        return
    welcomed = set(state["welcomed"] or [])
    for chat_id in CHAT_IDS:
        if id_hash(chat_id) in welcomed:
            continue
        try:
            telegram_sender("sendMessage", chat_id=chat_id,
                            text=f"✅ You're now following new birds for adoption on {PAGE}\n"
                                 "You'll get a message here when a new bird is posted "
                                 "(checked twice a day (around 11 and 18).")
            welcomed.add(id_hash(chat_id))
        except Exception as e:
            print(f"could not welcome {chat_id}:", e, flush=True)
    # Forget removed receivers, so they're welcomed again if re-added
    state["welcomed"] = [h for h in welcomed if h in current]


def check_new_posts(state):
    listings = parse_listings(fetch(PAGE))
    if not listings:
        raise RuntimeError("found 0 listings - page layout may have changed")
    if state["seen"] is None:
        # First run: remember what's there now
        state["seen"] = list(listings)
        save_state(state)
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
    welcome_new_receivers(state)
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


def mask(value):
    if IN_GITHUB_ACTIONS:
        print(f"::add-mask::{value}", flush=True)


def add_subscribers():
    """Find people who messaged the bot "add me" and write to receiver list to CHAT_IDS_OUT and notify me"""
    new = {}
    for update in telegram_sender("getUpdates").get("result", []):
        msg = update.get("message") or {}
        chat = msg.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        if chat.get("type") == "private" and ADD_ME_RE.search(msg.get("text") or "") and chat_id not in CHAT_IDS:
            mask(chat_id)
            name = " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")]))
            new[chat_id] = f"{name}" + (f" @{chat['username']}" if chat.get("username") else "") + f": {chat_id}"
    print(f"{len(new)} new subscriber(s)", flush=True)
    if not new:
        return
    with open(CHAT_IDS_OUT, "w") as f:
        f.write(",".join(CHAT_IDS + list(new)))
    try:
        telegram_sender("sendMessage", chat_id=ADMIN_CHAT_ID,
                        text="➕ Added to the receiver list (they get a welcome on the next check):\n"
                             + "\n".join(new.values())
                             + "\n\nFull list now in TELEGRAM_CHAT_ID:\n" + ",".join(CHAT_IDS + list(new)))
    except Exception as e:
        print("could not notify admin:", e, flush=True)


def main():
    if not TOKEN:
        sys.exit("Set TELEGRAM_TOKEN")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "loop"
    if cmd == "chatid":
        return print_chat_id()
    if not CHAT_IDS:
        sys.exit("Set TELEGRAM_CHAT_ID (run `python3 bot.py chatid` to find it)")
    for chat_id in CHAT_IDS:
        mask(chat_id)
    if cmd == "subscribers":
        return add_subscribers()
    if cmd == "once":
        return run_check_once()
    while True:
        run_check_once()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
