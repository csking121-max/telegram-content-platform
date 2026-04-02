# API Reference

Base URL: `http://localhost:8000`

## Authentication

Admin endpoints require a JWT token obtained via the login endpoint.  
Include the token in the `Authorization` header:

```
Authorization: Bearer <token>
```

---

## Public Endpoints

### Health Check

```
GET /health
```

Returns service status with database and Redis connectivity checks.

**Response:**
```json
{
  "status": "healthy",
  "checks": {
    "api": true,
    "database": true,
    "redis": true
  }
}
```

### Admin Login

```
POST /auth/login
```

**Request Body:**
```json
{
  "username": "admin",
  "password": "your-password"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

### Webhook (Bot → Backend)

```
POST /webhook/{bot_username}
```

**Headers:**
- `Content-Type: application/json`
- `X-Signature: <hmac-sha256-hex>`

**Request Body:**
```json
{
  "telegram_id": 123456789,
  "username": "user123",
  "action": "access_check",
  "token": "abc123...",
  "pack_id": null,
  "extra": {}
}
```

Actions: `access_check`, `request_delivery`

### Access Check

```
POST /access/check
```

**Request Body:**
```json
{
  "telegram_id": 123456789,
  "token": "abc123...",
  "bot_username": "mybot"
}
```

**Response (allowed):**
```json
{
  "allowed": true,
  "pack_id": 1,
  "reason": null,
  "upgrade_options": null
}
```

**Response (denied → 403):**
```json
{
  "detail": "Insufficient credits (need 50, have 10)."
}
```

### Payment Verification

```
POST /payments/verify
```

**Request Body:**
```json
{
  "reference": "PAY-001",
  "status": "completed",
  "provider_data": {}
}
```

---

## Admin Endpoints (JWT Required)

All admin endpoints are prefixed with `/admin`.

### Users

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/users` | List users (limit, offset) |
| GET | `/admin/users/count` | Total user count |
| GET | `/admin/users/{id}` | Get user by ID |
| POST | `/admin/users` | Create user |
| PATCH | `/admin/users/{id}` | Update user |
| POST | `/admin/users/{id}/block` | Block user (until datetime) |
| POST | `/admin/users/{id}/unblock` | Unblock user |
| DELETE | `/admin/users/{id}` | Delete user |

### Bots

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/bots` | List all bots |
| GET | `/admin/bots/active` | List active bots |
| GET | `/admin/bots/{id}` | Get bot by ID |
| POST | `/admin/bots` | Register new bot |
| PATCH | `/admin/bots/{id}` | Update bot |
| DELETE | `/admin/bots/{id}` | Delete bot |

**Create Bot Request:**
```json
{
  "bot_username": "new_bot",
  "bot_token": "123:ABC",
  "webhook_secret": "hmac_secret"
}
```

### Content Packs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/content-packs` | List all packs |
| GET | `/admin/content-packs/{id}` | Get pack with items |
| POST | `/admin/content-packs` | Create pack |
| PATCH | `/admin/content-packs/{id}` | Update pack |
| DELETE | `/admin/content-packs/{id}` | Delete pack |

### Pack Items

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/pack-items/{pack_id}` | List items in pack |
| POST | `/admin/pack-items/{pack_id}` | Add single item |
| POST | `/admin/pack-items/{pack_id}/bulk` | Add multiple items |
| DELETE | `/admin/pack-items/{item_id}` | Delete item |

### Tokens

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/tokens` | List tokens (limit, offset) |
| GET | `/admin/tokens/{token_str}` | Get token by string |
| POST | `/admin/tokens` | Create new token |
| DELETE | `/admin/tokens/{token_str}` | Revoke token |

**Create Token Request:**
```json
{
  "pack_id": 1,
  "expires_in_hours": 48,
  "single_use": true,
  "bound_user_id": null
}
```

### Credits

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/credits/{user_id}` | Get user balance |
| POST | `/admin/credits/{user_id}/adjust` | Add/deduct credits |
| POST | `/admin/credits/{user_id}/set` | Admin set balance |
| GET | `/admin/credits/{user_id}/history` | Credit history |

### Memberships

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/memberships/{user_id}` | User memberships |
| GET | `/admin/memberships/{user_id}/active` | Active memberships |
| POST | `/admin/memberships/{user_id}/grant` | Grant membership |
| POST | `/admin/memberships/{membership_id}/revoke` | Revoke membership |

### Referrals

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/referrals/{user_id}` | User referrals |
| GET | `/admin/referrals/{user_id}/count` | Successful count |
| POST | `/admin/referrals/{user_id}/invite` | Create invite code |
| GET | `/admin/referrals/code/{code}` | Lookup by code |

### Analytics

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/analytics/summary` | Dashboard counts |
| GET | `/admin/analytics/activity` | Recent activity logs |
| GET | `/admin/analytics/user/{user_id}` | User activity |
| GET | `/admin/analytics/revenue` | Revenue aggregates |

**Summary Response:**
```json
{
  "total_users": 1500,
  "total_bots": 3,
  "total_packs": 25,
  "total_deliveries": 12500,
  "total_payments": 850
}
```

---

## Error Responses

All errors follow the standard format:

```json
{
  "detail": "Error description"
}
```

| Status | Meaning |
|--------|---------|
| 400 | Bad request / Unknown action |
| 401 | Invalid credentials / Invalid JWT |
| 403 | Access denied / Invalid HMAC |
| 404 | Resource not found |
| 422 | Validation error |
| 429 | Rate limit exceeded |
| 500 | Internal server error |