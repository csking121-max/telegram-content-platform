"""Retroactively grant credits for verified credit package orders that never got fulfilled."""
import sqlite3

conn = sqlite3.connect("data/platform.db")
c = conn.cursor()

# Find verified credit package orders (plan_id=0)
c.execute(
    "SELECT id, order_ref, user_id, amount, package_id FROM payment_orders "
    "WHERE plan_id=0 AND status='verified'"
)
orders = c.fetchall()
print(f"Found {len(orders)} verified credit package orders")

# Get credit packages
c.execute("SELECT id, credits, price_inr FROM credit_packages")
packages = {row[0]: row for row in c.fetchall()}
print(f"Packages: {packages}")

# Check each order
for oid, order_ref, user_id, amount, package_id in orders:
    # Get current balance from credits table
    c.execute("SELECT balance FROM credits WHERE user_id=?", (user_id,))
    row = c.fetchone()
    old_balance = row[0] if row else 0

    # Check if credits were already granted (look in credit_history)
    c.execute(
        "SELECT id FROM credit_history WHERE user_id=? AND reason LIKE ?",
        (user_id, f"%{order_ref}%"),
    )
    if c.fetchone():
        print(f"  [SKIP] Credits already granted for order {order_ref} (user {user_id})")
        continue

    # Resolve package
    pkg = None
    if package_id and package_id in packages:
        pkg = packages[package_id]
    else:
        # Fallback: match by price
        for pid, pdata in packages.items():
            if pdata[2] == amount:  # price_inr
                pkg = pdata
                break

    if not pkg:
        print(f"  [SKIP] No matching package for order {order_ref} (amount={amount})")
        continue

    credits_to_add = pkg[1]  # credits field
    new_balance = old_balance + credits_to_add

    # Update or insert credits balance
    if row:
        c.execute("UPDATE credits SET balance=? WHERE user_id=?", (new_balance, user_id))
    else:
        c.execute("INSERT INTO credits (user_id, balance) VALUES (?, ?)", (user_id, new_balance))

    # Insert credit history
    c.execute(
        "INSERT INTO credit_history (user_id, change_amount, reason, created_at) "
        "VALUES (?, ?, ?, datetime('now'))",
        (user_id, credits_to_add, f"credit_purchase:retrofix:{order_ref}"),
    )

    print(f"  [FIXED] Order {order_ref}: user {user_id} got +{credits_to_add} credits ({old_balance} -> {new_balance})")

conn.commit()
conn.close()
print("Done!")
