import sqlite3
conn = sqlite3.connect("data/platform.db")
c = conn.cursor()

# Check if streak_levels table exists
c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='streak_levels'")
print("streak_levels table:", c.fetchone())

# Check user_streaks columns 
c.execute("PRAGMA table_info(user_streaks)")
cols = [r[1] for r in c.fetchall()]
print("user_streaks columns:", cols)

# Apply missing columns if needed
if "current_level" not in cols:
    print("Adding current_level and last_level_claimed columns...")
    c.execute("ALTER TABLE user_streaks ADD COLUMN current_level INTEGER NOT NULL DEFAULT 0")
    c.execute("ALTER TABLE user_streaks ADD COLUMN last_level_claimed INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    print("Columns added!")
else:
    print("Columns already exist.")

# Create streak_levels table if missing
c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='streak_levels'")
if not c.fetchone():
    print("Creating streak_levels table...")
    c.execute("""
        CREATE TABLE streak_levels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level INTEGER NOT NULL UNIQUE,
            streak_days_required INTEGER NOT NULL UNIQUE,
            bonus_credits INTEGER NOT NULL DEFAULT 0,
            membership_plan_id INTEGER REFERENCES membership_plans(id) ON DELETE SET NULL,
            membership_duration_days INTEGER NOT NULL DEFAULT 0,
            label VARCHAR(128) NOT NULL DEFAULT '',
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("CREATE INDEX ix_streak_levels_level ON streak_levels(level)")
    conn.commit()
    print("streak_levels table created!")
else:
    print("streak_levels table already exists.")

conn.close()
print("Done.")
