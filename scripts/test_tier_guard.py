"""Test Phase 14: Tier guard + credit streak integration."""
import sqlite3
import requests

BASE = "http://127.0.0.1:8000"

def main():
    # Check DB state
    conn = sqlite3.connect("data/platform.db")
    c = conn.cursor()
    
    print("=== Membership Plans ===")
    c.execute("SELECT id, name, tier_level, access_type, credit_price FROM membership_plans ORDER BY tier_level")
    for r in c.fetchall():
        print(f"  id={r[0]} name={r[1]} tier={r[2]} type={r[3]} credits={r[4]}")
    
    print("\n=== User 3 Active Memberships ===")
    c.execute("SELECT id, membership_type, expiry_at FROM memberships WHERE user_id=3 AND expiry_at > '2026-03-07T20:00:00'")
    for r in c.fetchall():
        print(f"  id={r[0]} type={r[1]} expiry={r[2]}")
    
    conn.close()
    
    # Test 1: Profile returns max_tier_level
    print("\n=== Test 1: Profile max_tier_level ===")
    r = requests.get(f"{BASE}/access/profile/6189058729", timeout=5)
    data = r.json()
    max_tier = data.get("max_tier_level", "MISSING")
    print(f"  Status: {r.status_code}, max_tier_level: {max_tier}")
    
    # Test 2: Try to buy plan with credits at same or lower tier (should fail)
    print("\n=== Test 2: Buy same-tier plan with credits (should FAIL) ===")
    # VIP is tier 2, user has tier 2 active
    r = requests.post(f"{BASE}/payments/buy-with-credits", json={
        "telegram_id": 6189058729,
        "plan_id": 2,  # VIP, tier 2
    }, timeout=5)
    print(f"  Status: {r.status_code}")
    print(f"  Response: {r.json()}")
    
    # Test 3: Try to buy lower-tier plan with credits (should fail)
    print("\n=== Test 3: Buy lower-tier plan with credits (should FAIL) ===")
    # Premium is tier 1, user has tier 2 active
    r = requests.post(f"{BASE}/payments/buy-with-credits", json={
        "telegram_id": 6189058729,
        "plan_id": 3,  # premium, tier 1
    }, timeout=5)
    print(f"  Status: {r.status_code}")
    print(f"  Response: {r.json()}")
    
    # Test 4: Try to create UPI order for same-tier plan (should fail)
    print("\n=== Test 4: Create UPI order for same-tier plan (should FAIL) ===")
    r = requests.post(f"{BASE}/payments/create-order", json={
        "telegram_id": 6189058729,
        "plan_id": 2,  # VIP, tier 2
    }, timeout=5)
    print(f"  Status: {r.status_code}")
    print(f"  Response: {r.json()}")
    
    # Test 5: User without memberships can still buy (user 2)
    print("\n=== Test 5: User without memberships can buy with credits ===")
    # First check credits
    r2 = requests.get(f"{BASE}/access/profile/6605811714", timeout=5)
    d2 = r2.json()
    print(f"  User 2 credits: {d2.get('credits')}, max_tier: {d2.get('max_tier_level')}")
    
    # Try to buy with credits (may fail due to insufficient credits, but NOT tier guard)
    r = requests.post(f"{BASE}/payments/buy-with-credits", json={
        "telegram_id": 6605811714,
        "plan_id": 2,  # VIP, tier 2
    }, timeout=5)
    print(f"  Status: {r.status_code}")
    resp = r.json()
    detail = resp.get("detail", "")
    if "tier" in detail.lower() or "already" in detail.lower():
        print(f"  FAIL: Tier guard should NOT block this user! Detail: {detail}")
    else:
        print(f"  OK: {resp}")
    
    print("\n=== All tests done ===")


if __name__ == "__main__":
    main()
