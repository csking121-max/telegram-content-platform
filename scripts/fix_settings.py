"""Clean up payment settings in database."""
import sqlite3

conn = sqlite3.connect("data/platform.db")
c = conn.cursor()

# Remove sms_forward_api_key
c.execute("DELETE FROM platform_settings WHERE key='sms_forward_api_key'")
print(f"Deleted sms_forward_api_key: {c.rowcount} rows")

# Update payment_expiry_minutes default to 15
c.execute(
    "UPDATE platform_settings SET value='15', description='Minutes before a payment order expires (default: 15)' "
    "WHERE key='payment_expiry_minutes'"
)
print(f"Updated payment_expiry_minutes: {c.rowcount} rows")

# Move utr_group_chat_id to payment category and update description
c.execute(
    "UPDATE platform_settings SET description='Telegram group ID where bank SMS are forwarded for UTR verification', "
    "category='payment' WHERE key='utr_group_chat_id'"
)
print(f"Updated utr_group_chat_id: {c.rowcount} rows")

# Verify
c.execute("SELECT key, value, category, description FROM platform_settings WHERE category='payment'")
for row in c.fetchall():
    print(f"  {row[0]} = {row[1]} ({row[2]}) - {row[3]}")

conn.commit()
conn.close()
print("Done!")
