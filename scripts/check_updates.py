"""Check for pending Telegram updates — run with gateway STOPPED."""
import sqlite3
import urllib.request
import json

conn = sqlite3.connect("data/platform.db")
c = conn.cursor()
c.execute("SELECT bot_token FROM bots LIMIT 1")
token = c.fetchone()[0]

print(f"Bot token: ...{token[-8:]}")
print("Fetching updates (5s timeout)...")

url = f"https://api.telegram.org/bot{token}/getUpdates?limit=10&timeout=5"
r = json.loads(urllib.request.urlopen(url).read())

updates = r.get("result", [])
print(f"\nTotal updates: {len(updates)}")

for u in updates:
    uid = u.get("update_id")
    msg = u.get("message") or u.get("channel_post") or {}
    chat = msg.get("chat", {})
    from_user = msg.get("from", {})
    text = msg.get("text", "") or msg.get("caption", "") or ""

    chat_id = chat.get("id", "?")
    chat_type = chat.get("type", "?")
    chat_title = chat.get("title", "")
    from_name = from_user.get("username") or from_user.get("first_name") or "?"
    is_bot_flag = from_user.get("is_bot", False)
    from_id = from_user.get("id", "?")

    print(f"\n--- Update {uid} ---")
    print(f"  Chat: {chat_id} ({chat_type}) title='{chat_title}'")
    print(f"  From: {from_name} (id={from_id}, is_bot={is_bot_flag})")
    if text:
        print(f"  Text: {text[:200]}")
    else:
        keys = [k for k in msg.keys() if k not in ("chat", "from", "date", "message_id")]
        print(f"  [No text] Other keys: {keys}")
