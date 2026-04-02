"""Apply migration 010 — add performance indexes."""
import sqlite3
import os

db_path = os.path.join("data", "platform.db")
if not os.path.exists(db_path):
    print("DB not found, indexes will be created on next startup")
    exit(0)

conn = sqlite3.connect(db_path)
c = conn.cursor()

indexes = [
    ("ix_delivered_messages_delete_at", "delivered_messages", "delete_at"),
    ("ix_payment_orders_status", "payment_orders", "status"),
    ("ix_content_packs_access_type", "content_packs", "access_type"),
    ("ix_platform_settings_category", "platform_settings", "category"),
]

for idx_name, table, col in indexes:
    try:
        c.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({col})")
        print(f"Created index {idx_name}")
    except Exception as e:
        print(f"Index {idx_name}: {e}")

conn.commit()

try:
    c.execute("UPDATE alembic_version SET version_num='010'")
    if c.rowcount == 0:
        c.execute("INSERT INTO alembic_version VALUES('010')")
    conn.commit()
    print("Alembic version updated to 010")
except Exception as e:
    print(f"Alembic update: {e}")

conn.close()
print("Done.")
