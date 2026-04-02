import sqlite3
conn = sqlite3.connect("data/platform.db")
c = conn.cursor()
c.execute("SELECT key, value FROM platform_settings WHERE category='streak'")
for r in c.fetchall():
    print(r)
print()
c.execute("SELECT * FROM user_streaks WHERE user_id=2")
for r in c.fetchall():
    print("user_streak:", r)
c.execute("SELECT * FROM credit_history WHERE user_id=2 ORDER BY id DESC LIMIT 5")
for r in c.fetchall():
    print("credit_history:", r)
conn.close()
