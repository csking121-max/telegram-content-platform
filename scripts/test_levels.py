"""Test streak level API endpoints."""
import requests

BASE = "http://localhost:8000"

# Login
r = requests.post(f"{BASE}/auth/login", json={"username": "admin", "password": "admin"})
print(f"Login: {r.status_code}")
token = r.json().get("access_token", "")
h = {"Authorization": f"Bearer {token}"}

# List levels (should be empty)
r = requests.get(f"{BASE}/admin/streaks/levels", headers=h)
print(f"List levels: {r.status_code} -> {r.json()}")

# Create levels
for lvl, days, credits, label in [(1, 10, 50, "Beginner"), (2, 20, 120, "Intermediate"), (3, 30, 250, "Expert")]:
    r = requests.post(f"{BASE}/admin/streaks/levels", headers=h, json={
        "level": lvl, "streak_days_required": days, "bonus_credits": credits, "label": label,
    })
    print(f"  Create Lv.{lvl}: {r.status_code} -> {r.json()}")

# List again
r = requests.get(f"{BASE}/admin/streaks/levels", headers=h)
print(f"\nList levels: {r.status_code}")
for lv in r.json():
    plan = lv.get("membership_plan_id")
    print(f"  Lv.{lv['level']} ({lv['streak_days_required']}d) -> +{lv['bonus_credits']}c | plan={plan} | {lv['label']}")

# Get membership plans
r = requests.get(f"{BASE}/admin/streaks/membership-plans", headers=h)
print(f"\nMembership plans: {r.status_code} -> {len(r.json())} plans")
for p in r.json():
    print(f"  {p['id']}: {p['display_name']} ({p['access_type']})")

# Test update: set Level 3 to give membership
plans = r.json()
if plans:
    plan_id = plans[0]["id"]
    # Get the level 3 id
    levels = requests.get(f"{BASE}/admin/streaks/levels", headers=h).json()
    lv3 = [l for l in levels if l["level"] == 3]
    if lv3:
        r = requests.patch(f"{BASE}/admin/streaks/levels/{lv3[0]['id']}", headers=h, json={
            "membership_plan_id": plan_id, "membership_duration_days": 7,
        })
        print(f"\nUpdate Lv.3 with membership: {r.status_code}")
        lv = r.json()
        print(f"  plan_id={lv.get('membership_plan_id')}, mem_days={lv.get('membership_duration_days')}")

print("\nAll level tests passed!")
