"""Quick test: announce + track-messages endpoints."""
import httpx
import sqlite3

BASE = "http://localhost:8000"
DB = r"d:\TG SYSTEM\telegram-content-platform\data\platform.db"

conn = sqlite3.connect(DB)
c = conn.cursor()
users = c.execute("SELECT telegram_id FROM users").fetchall()
dm = c.execute("SELECT COUNT(*) FROM delivered_messages").fetchone()
bm = c.execute("SELECT COUNT(*) FROM bot_messages").fetchone()
bots = c.execute("SELECT id, bot_username FROM bots WHERE status='active'").fetchall()
conn.close()

print(f"Users: {[u[0] for u in users]}")
print(f"delivered_messages count: {dm[0]}")
print(f"bot_messages count: {bm[0]}")
print(f"Active bots: {bots}")

if not bots:
    print("No active bots found!")
    exit(1)

bot_id = bots[0][0]
print(f"\n--- Testing track-messages with bot_id={bot_id} ---")
r = httpx.post(f"{BASE}/internal/track-messages", json=[{
    "bot_id": bot_id,
    "chat_id": users[0][0] if users else 123,
    "message_id": 12345,
    "direction": "in"
}], timeout=10)
print(f"track-messages: {r.status_code} {r.text}")

print(f"\n--- Testing announce with bot_id={bot_id} ---")
r2 = httpx.post(f"{BASE}/internal/bots/{bot_id}/announce", json={"message": "Hello test!"}, timeout=30)
print(f"announce: {r2.status_code} {r2.text}")

print(f"\n--- Testing send-welcome with bot_id={bot_id} ---")
r3 = httpx.post(f"{BASE}/internal/bots/{bot_id}/send-welcome", timeout=30)
print(f"send-welcome: {r3.status_code} {r3.text}")
