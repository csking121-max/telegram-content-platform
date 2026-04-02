"""Live test: send a message, track it, then delete it via clear-messages endpoint."""
import sqlite3
import urllib.request
import json
import time

conn = sqlite3.connect('data/platform.db')
c = conn.cursor()
c.execute('SELECT id, bot_token FROM bots WHERE status="active" LIMIT 1')
row = c.fetchone()
bot_db_id, token = row
conn.close()

chat_id = 6605811714  # ankiitashaarma - real user


def tg(method, data):
    url = f'https://api.telegram.org/bot{token}/{method}'
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def api_post(path, data=None):
    url = f'http://localhost:8000{path}'
    body = json.dumps(data).encode() if data else b'{}'
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


print(f"Bot DB id={bot_db_id}, chat_id={chat_id}")
print()

# Step 1: Send a test message directly via Telegram API
print("=== STEP 1: Send test message ===")
r = tg('sendMessage', {'chat_id': chat_id, 'text': 'TEST DELETE - this message should disappear after ~5 seconds'})
print("Send ok:", r.get('ok'))
msg_id = r['result']['message_id']
print("Message ID:", msg_id)
print()

# Step 2: Manually track it via the backend
print("=== STEP 2: Track the message ===")
r2 = api_post('/internal/track-messages', [
    {'bot_id': bot_db_id, 'chat_id': chat_id, 'message_id': msg_id, 'direction': 'out'}
])
print("Track result:", r2)
print()

time.sleep(3)

# Step 3: Call clear-messages
print("=== STEP 3: Call clear-messages ===")
r3 = api_post(f'/internal/bots/{bot_db_id}/clear-messages')
print("Clear result:", r3)
print()

# Step 4: Try to delete again — should fail if already deleted
print("=== STEP 4: Verify deleted (re-delete should fail) ===")
r4 = tg('deleteMessage', {'chat_id': chat_id, 'message_id': msg_id})
print("Re-delete ok:", r4.get('ok'), "| error:", r4.get('description', 'none'))

# Step 5: Check DB is empty
print()
conn2 = sqlite3.connect('data/platform.db')
c2 = conn2.cursor()
c2.execute('SELECT COUNT(*) FROM bot_messages')
print("bot_messages in DB after clear:", c2.fetchone()[0])
conn2.close()
