# 📱 SMS Forwarding & UTR Verification Setup

This guide explains how to set up automatic payment verification using SMS forwarding from your Android phone to the TCAP backend.

---

## How It Works

1. User pays via UPI → bank sends an SMS confirmation with UTR number
2. Android SMS forwarding app on **your phone** catches incoming bank SMS
3. The app sends the SMS to your **TCAP backend** via HTTP webhook
4. Backend extracts the UTR + amount, auto-matches against pending payment orders
5. If a match is found, the order is verified and user access is granted automatically
6. User gets a Telegram notification: "✅ Payment Verified!"
7. The SMS is also forwarded to your **UTR Verification group** for admin visibility

> **Important:** We use the **URL/Webhook mode** of the SMS Forwarder app (NOT the Telegram mode).
> Telegram bots cannot see messages from other bots in groups — this is a Telegram limitation.

---

## Prerequisites

- An Android phone that receives UPI payment confirmation SMS
- A Telegram group for UTR verification (for admin visibility)
- Your TCAP backend running and accessible from your phone (same Wi-Fi, or public URL via ngrok)

---

## Step 1: Create the UTR Verification Group

1. Create a new Telegram group (e.g. "UTR Verification")
2. Add your TCAP bot to the group as an **admin**
3. Get the group chat ID (it will look like `-1003722286878`)
   - You can use `@userinfobot` or `@getidsbot` in the group to find it

---

## Step 2: Configure in Admin Panel

Go to your TCAP Admin Panel → **Settings** and set:

| Setting | Value |
|---------|-------|
| `utr_group_chat_id` | `-1003722286878` (your group chat ID) |
| `platform_name` | Your platform name |
| `support_contact` | `@your_support_username` |

Click **Save All Settings**.

---

## Step 3: Set Up SMS Forwarding App (Android)

### Recommended: **SMS Forwarder** (by paixaop or similar)

1. Install any SMS Forwarder app from the Play Store
2. Choose **URL/Webhook** mode (NOT Telegram mode)
3. Set the webhook URL to your backend:

#### If backend is on the same Wi-Fi network:
```
http://<YOUR_PC_IP>:8000/sms/webhook
```
Example: `http://192.168.1.100:8000/sms/webhook`

To find your PC's IP, open PowerShell and run:
```powershell
ipconfig | findstr "IPv4"
```

#### If backend is exposed via ngrok:
```
https://<YOUR_NGROK_URL>/sms/webhook
```

4. Set method to **POST**
5. Set content type to **JSON** (application/json)
6. Add a **filter rule** for bank SMS senders:
   - `PYTUPI`, `GPAYUPI`, `PHONPE`, `PAYTM`, `AXISBK`, `SBIINB`, `HDFCBK`, `ICICIB`, `KOTAKB`

### What the webhook accepts:

The endpoint auto-detects common field names. Any of these formats work:

```json
{"from": "HDFCBK", "text": "Rs.299.00 credited to A/c XX1234 by UPI Ref 412345678901"}
```
```json
{"sender": "KOTAKB", "body": "Received Rs.299.00 in your Kotak Bank AC ..."}
```
```json
{"number": "+91XXXXX", "message": "Rs.299 credited ... UPI Ref 412345678901"}
```

Supported text fields: `text`, `body`, `message`, `smsBody`, `msg`, `content`
Supported sender fields: `from`, `sender`, `number`, `address`, `phone`, `sim`

---

## Step 4: Test the Setup

### Quick test from PowerShell:
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/sms/webhook" -Method POST -ContentType "application/json" -Body '{"from":"HDFCBK","text":"Rs.299.00 credited to A/c XX1234 by UPI Ref 412345678901"}'
```

Expected response:
```json
{"status": "ok", "utr": "412345678901", "matched": false}
```

If there's a pending order with that UTR, `matched` will be `true` and the user gets notified automatically.

### Test from your phone:
Open a browser on your phone and navigate to `http://<YOUR_PC_IP>:8000/docs` — if you see the API docs page, the phone can reach the backend.

---

## Step 5: Android Permissions

Make sure the forwarding app has these permissions:
- **Receive SMS** (READ_SMS, RECEIVE_SMS)
- **Internet access**
- **Run in background** (disable battery optimization)
- **Autostart** (on Xiaomi/MIUI, enable autostart for the app)

### For Xiaomi/MIUI devices:
1. Settings → Battery → App battery saver → SMS Forwarder → No restrictions
2. Settings → Apps → Manage apps → SMS Forwarder → Autostart → Enable
3. Lock the app in recent apps tray

### For Samsung OneUI:
1. Settings → Apps → SMS Forwarder → Battery → Unrestricted

### For stock Android:
1. Settings → Apps → SMS Forwarder → Battery → Unrestricted

---

## Common Bank SMS Patterns (India)

The system extracts UTR from these SMS formats:

| Bank | Example SMS | UTR Pattern |
|------|------------|-------------|
| HDFC | `Rs.299.00 credited by UPI Ref 412345678901` | 12-digit UPI ref |
| SBI  | `credited by transfer INR 299 Ref no 412345678901` | Ref no |
| ICICI | `Cr INR 299.00 in Acct by UPI Ref:412345678901` | UPI Ref: |
| Axis | `Rs.299 has been credited, UTR: 412345678901` | UTR: |
| Kotak | `Received Rs.299, IMPS Ref 412345678901234` | IMPS Ref |
| GPay/PhonePe | `You received ₹299. UPI Ref ID: 412345678901` | Ref ID: |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| SMS not reaching backend | Check phone and PC are on same Wi-Fi; test `http://<IP>:8000/docs` from phone browser |
| SMS forwarded but UTR not extracted | Check SMS format; patterns are in `sms_verification_service.py` |
| Order not auto-matched | User must submit UTR via `/pay` first; order must be in `utr_submitted` status |
| Phone can't reach server | Check Windows Firewall allows port 8000; or use `ngrok http 8000` for external access |
| App stops forwarding after a while | Disable battery optimization, enable autostart for the app |
| UTR group not showing forwarded SMS | Check `utr_group_chat_id` is set correctly in Admin → Settings |
