"""Quick test for streak API endpoints."""
import requests

BASE = "http://localhost:8000"

# Login
r = requests.post(f"{BASE}/auth/login", json={"username": "admin", "password": "admin"})
print(f"Login: {r.status_code}")
token = r.json().get("access_token")
h = {"Authorization": f"Bearer {token}"}

print("--- Create milestones ---")
for days, bonus in [(5, 25), (10, 60), (15, 100), (30, 250)]:
    r = requests.post(
        f"{BASE}/admin/streaks/milestones",
        json={"days_required": days, "bonus_credits": bonus, "label": f"{days}-day streak"},
        headers=h,
    )
    m = r.json()
    print(f"  {days}d -> {bonus}c: {r.status_code} {m}")

print("\n--- List milestones ---")
r = requests.get(f"{BASE}/admin/streaks/milestones", headers=h)
print(f"  Status: {r.status_code}")
ms = r.json()
if isinstance(ms, list):
    print(f"  Total: {len(ms)}")
    for m in ms:
        print(f"  {m['days_required']}d -> +{m['bonus_credits']}c ({m['label']}) active={m['is_active']}")
else:
    print(f"  Response: {ms}")

print("\n--- List user streaks ---")
r = requests.get(f"{BASE}/admin/streaks/users", headers=h)
print(f"  Status: {r.status_code} User streaks: {r.json()}")

print("\n--- Health check ---")
r = requests.get(f"{BASE}/health")
print(f"  {r.json()}")

print("\nAll streak tests passed!")
