"""Check recent updates from Telegram to see UTR group messages."""
import sqlite3
import urllib.request
import json

conn = sqlite3.connect("data/platform.db")
c = conn.cursor()
c.execute("SELECT bot_token FROM bots LIMIT 1")
token = c.fetchone()[0]

# Get recent updates
url = f"https://api.telegram.org/bot{token}/getUpdates?limit=20&offset=-20"
r = json.loads(urllib.request.urlopen(url).read())

print(f"Total updates: {len(r.get('result', []))}")
print("=" * 80)

for u in r.get("result", []):
    uid = u.get("update_id")
    msg = u.get("message") or u.get("channel_post") or {}
    chat = msg.get("chat", {})
    from_user = msg.get("from", {})
    text = msg.get("text", "") or msg.get("caption", "") or ""
    fwd = msg.get("forward_from") or msg.get("forward_from_chat")

    chat_id = chat.get("id", "?")
    chat_type = chat.get("type", "?")
    chat_title = chat.get("title", "")
    from_name = from_user.get("username") or from_user.get("first_name") or "?"
    is_bot = from_user.get("is_bot", False)

    print(f"Update {uid}: chat={chat_id} ({chat_type}) title='{chat_title}'")
    print(f"  From: {from_name} (is_bot={is_bot})")
    if fwd:
        print(f"  Forwarded from: {fwd}")
    if text:
        print(f"  Text: {text[:200]}")
    else:
        print(f"  [No text/caption] Keys: {list(msg.keys())}")
    print()
