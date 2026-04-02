import sqlite3
conn = sqlite3.connect(r'd:\TG SYSTEM\telegram-content-platform\data\platform.db')
c = conn.cursor()
tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
bot_tables = [t[0] for t in tables if 'bot' in t[0].lower()]
print('Bot-related tables:', bot_tables)
if 'bot_messages' in [t[0] for t in tables]:
    cols = c.execute("PRAGMA table_info(bot_messages)").fetchall()
    print('bot_messages columns:', [r[1] for r in cols])
else:
    print('bot_messages table NOT found')
cols = c.execute("PRAGMA table_info(bots)").fetchall()
print('bots columns:', [r[1] for r in cols])
conn.close()
