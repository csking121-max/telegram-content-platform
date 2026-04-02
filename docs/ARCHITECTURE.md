# Architecture Overview

## System Architecture

The Telegram Content Access Platform is a production-grade SaaS system designed to serve **100,000+ users** across **multiple Telegram bots**, all connected to a single backend.

```
┌──────────────────────────────────────────────────────────────────────┐
│                        TELEGRAM CHANNELS                            │
│   Channel A ──► Deep Link    Channel B ──► Deep Link    ...         │
│   (t.me/bot1?start=TOKEN)   (t.me/bot2?start=TOKEN)               │
└────────────┬─────────────────────────┬───────────────────────────────┘
             │                         │
┌────────────▼─────────┐  ┌────────────▼─────────┐
│   Telegram Bot 1     │  │   Telegram Bot 2     │   (aiogram 3.x)
│   (Thin Gateway)     │  │   (Thin Gateway)     │
│   • Parse /start     │  │   • Parse /start     │
│   • Extract token    │  │   • Extract token    │
│   • HMAC sign        │  │   • HMAC sign        │
│   • Forward to API   │  │   • Forward to API   │
└────────────┬─────────┘  └────────────┬─────────┘
             │     POST /webhook/{bot}  │
             ▼                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     FASTAPI BACKEND (:8000)                         │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │ Webhook API  │  │ Access API   │  │ Admin API (JWT-protected) │  │
│  │ /webhook/*   │  │ /access/*    │  │ /admin/*                  │  │
│  └──────┬───────┘  └──────┬───────┘  └────────────┬──────────────┘  │
│         │                  │                       │                 │
│  ┌──────▼──────────────────▼───────────────────────▼──────────────┐  │
│  │                    ENGINE LAYER                                │  │
│  │  AccessControlEngine │ CreditEngine │ DeliveryEngine          │  │
│  │  TokenService        │ MembershipEngine                       │  │
│  └──────┬──────────────────────────────────────────┬──────────────┘  │
│         │                                          │                 │
│  ┌──────▼──────────┐                    ┌──────────▼──────────┐     │
│  │  SERVICE LAYER  │                    │    SECURITY LAYER   │     │
│  │  UserService    │                    │    HMAC Validation  │     │
│  │  BotService     │                    │    Rate Limiter     │     │
│  │  PaymentService │                    │    Anti-Abuse Guard │     │
│  │  ReferralService│                    │    JWT Auth         │     │
│  │  ActivityLogger │                    └─────────────────────┘     │
│  └────────┬────────┘                                                │
│           │                                                         │
└───────────┼─────────────────────────────────────────────────────────┘
            │
    ┌───────▼───────┐          ┌─────────────────────┐
    │  PostgreSQL   │          │       Redis          │
    │  (15-alpine)  │          │    (7-alpine)        │
    │               │          │                      │
    │  • users      │          │  • queue:delivery    │
    │  • tokens     │          │  • queue:deletion    │
    │  • packs      │          │  • queue:credit      │
    │  • credits    │          │  • rate limit keys   │
    │  • payments   │          │  • cache             │
    │  • ...12 tables│         │                      │
    └───────────────┘          └──────────┬───────────┘
                                          │
                               ┌──────────▼───────────┐
                               │    WORKER SERVICES    │
                               │                       │
                               │  delivery_worker      │
                               │  • Sends messages via │
                               │    Telegram Bot API   │
                               │                       │
                               │  deletion_worker      │
                               │  • Deletes messages   │
                               │    after TTL          │
                               │                       │
                               │  credit_worker        │
                               │  • Processes credit   │
                               │    operations         │
                               │                       │
                               │  access_worker        │
                               │  • Async access checks│
                               └───────────────────────┘
```

## Key Design Principles

### 1. Bots Are Thin Gateways
Telegram bots contain **zero business logic**. They:
- Receive `/start` commands with deep-link tokens
- Extract `telegram_id`, `username`, and `token`
- Sign the payload with HMAC-SHA256
- Forward via HTTP POST to the backend's `/webhook/{bot_username}` endpoint

This means adding a new bot requires only registering it in the database and `.env` — no code changes.

### 2. Engine Layer (Stateless)
All business logic lives in engine classes:
- **AccessControlEngine** — 7-step access validation pipeline
- **CreditEngine** — Atomic credit mutations with history
- **DeliveryEngine** — Enqueues delivery jobs to Redis
- **TokenService** — Token creation, validation, usage tracking
- **MembershipEngine** — Membership lifecycle (grant, revoke, check)

Engines are **stateless** — instantiated per-request with an `AsyncSession`.

### 3. Async Everything
- FastAPI with `async def` endpoints
- SQLAlchemy 2.0 `AsyncSession` + `create_async_engine`
- `asyncpg` driver for PostgreSQL
- Workers use `asyncio` event loops

### 4. Queue-Based Processing
Content delivery and message deletion are **never done synchronously** in the request path:
1. Backend enqueues a job to Redis (`LPUSH`)
2. Worker polls the queue (`BRPOP`)
3. Worker performs the action (send message, delete message)
4. Worker records the result in PostgreSQL

### 5. Security Layers
- **HMAC-SHA256** — Every webhook from a bot is signed with a per-bot secret
- **JWT (HS256)** — Admin panel authentication
- **Rate Limiter** — Redis sliding-window counter per user
- **Anti-Abuse Guard** — Detects rapid token use and credit fraud

## Database Schema (12 Tables)

| Table | Purpose |
|-------|---------|
| `users` | Telegram users with level, blocked status |
| `bots` | Registered Telegram bots with tokens/secrets |
| `content_packs` | Groups of media with access rules |
| `pack_items` | Individual media files (photo/video/document/audio) |
| `tokens` | Access tokens with expiry, single-use, user binding |
| `credits` | One-to-one credit balance per user |
| `credit_history` | Audit trail of every credit change |
| `memberships` | User memberships (vip, premium, daily_pass) |
| `payments` | Payment records (pending → completed/failed) |
| `delivered_messages` | Tracks sent messages for auto-deletion |
| `referrals` | Invite codes with reward tracking |
| `activity_logs` | User action audit trail |

## Docker Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `backend` | `Dockerfile.backend` | 8000 | FastAPI + Uvicorn |
| `worker` | `Dockerfile.worker` | — | Redis queue processors |
| `admin` | `Dockerfile.admin` | 3000 | React admin panel (static) |
| `db` | `postgres:15-alpine` | 5432 | PostgreSQL database |
| `redis` | `redis:7-alpine` | 6379 | Queue + cache + rate limiting |