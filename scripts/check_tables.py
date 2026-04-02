import sqlite3
c = sqlite3.connect('data/platform.db').cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
print([r[0] for r in c.fetchall()])
c.execute("PRAGMA table_info(credits)")
print("credits cols:", [r[1] for r in c.fetchall()])
c.execute("PRAGMA table_info(credit_history)")
print("credit_history cols:", [r[1] for r in c.fetchall()])
