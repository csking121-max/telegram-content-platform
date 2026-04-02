"""Test if Telegram delivers other bot messages via getUpdates."""
import sqlite3
import urllib.request
import json
import time

conn = sqlite3.connect("data/platform.db")
c = conn.cursor()
c.execute("SELECT bot_token FROM bots LIMIT 1")
token = c.fetchone()[0]

print("Calling getUpdates (10s long-poll)...")
url = f"https://api.telegram.org/bot{token}/getUpdates?limit=10&timeout=10"
r = json.loads(urllib.request.urlopen(url).read())
updates = r.get("result", [])
print(f"Got {len(updates)} updates\n")

for u in updates:
    uid = u.get("update_id")
    msg = u.get("message", {})
    chat = msg.get("chat", {})
    fr = msg.get("from", {})
    text = msg.get("text", "") or msg.get("caption", "") or ""
    
    print(f"Update {uid}:")
    print(f"  Chat: {chat.get('id')} ({chat.get('type')}) title={chat.get('title','')}")
    print(f"  From: {fr.get('username','?')} (id={fr.get('id')}, is_bot={fr.get('is_bot')})")
    print(f"  Text: {text[:150]}")
    print()

if not updates:
    print("No pending updates. The other bot's message may have already been consumed by polling.")
    print("Try sending a NEW message from the other bot now and re-run this script.")
