# Telegram Content Access Platform

A production-grade SaaS platform for managing paid and free content access via Telegram bots. Supports 100k+ users, multiple bots, credit economy, memberships, referral programs, and a React admin panel.

```
┌──────────┐   ┌──────────┐   ┌──────────┐
│  Bot A   │   │  Bot B   │   │  Bot C   │   Telegram Bots
└────┬─────┘   └────┬─────┘   └────┬─────┘
     │              │              │
     └──────────────┼──────────────┘
                    │  webhooks
            ┌───────▼────────┐
            │  FastAPI API   │──── Admin UI (React)
            └───────┬────────┘
                    │
          ┌─────────┼─────────┐
          │         │         │
     ┌────▼──┐ ┌───▼───┐ ┌───▼────┐
     │ Postgres│ │ Redis │ │Workers │
     └────────┘ └───────┘ └────────┘
```

## Features

| Feature | Description |
|---------|-------------|
| **Multi-Bot Gateway** | Connect unlimited Telegram bots to a single backend |
| **Content Packs** | Group media items into packs, deliver via deep-link tokens |
| **Access Control Engine** | 7-step pipeline: user → bot → token → pack → type → credits/membership → deliver |
| **Credit System** | Earn, spend, admin-set credits with full audit trail |
| **Membership Tiers** | Time-based VIP/Premium access with auto-expiry |
| **Referral Program** | Invite codes, tracking, automatic credit rewards |
| **Anti-Abuse** | Rate limiting, fraud detection, HMAC webhook validation |
| **Background Workers** | Async delivery, deletion, credit processing via Redis queues |
| **Admin Panel** | React + TypeScript dashboard for full platform management |
| **Auto-Delete** | Scheduled deletion of delivered messages |

## Tech Stack

| Layer | Technology |
|-------|------------|
| API | Python 3.11, FastAPI 0.109, Pydantic 2.6 |
| Database | PostgreSQL 15, SQLAlchemy 2.0 (async), Alembic |
| Queue/Cache | Redis 7 |
| Telegram | aiogram 3.4 (multi-bot dispatcher) |
| Workers | Async Python consumers |
| Admin UI | React 18.2, TypeScript 5.3, Vite 5.1, React Router 6 |
| Auth | JWT (python-jose), bcrypt (passlib) |
| Containers | Docker, Docker Compose |
| Testing | pytest, pytest-asyncio, aiosqlite |

## Quick Start

```bash
# 1. Clone and configure
git clone <repository-url>
cd telegram-content-platform
cp .env.example .env
# Edit .env — set TELEGRAM_BOTS, ADMIN_PASSWORD, ADMIN_JWT_SECRET

# 2. Start everything
docker-compose up --build

# 3. Run database migrations
docker-compose exec backend alembic upgrade head

# 4. (Optional) Seed sample data
docker-compose exec backend python -m scripts.seed_db

# 5. Register Telegram webhooks
python scripts/register_webhooks.py --domain https://your-domain.com
```

### Services

| Service | URL | Description |
|---------|-----|-------------|
| Backend API | http://localhost:8000 | REST API + webhook receiver |
| Admin Panel | http://localhost:3000 | Management dashboard |
| Health Check | http://localhost:8000/health | Service health status |

## Project Structure

```
├── backend/
│   ├── main.py              # FastAPI app with lifespan
│   ├── config.py             # Settings (env vars)
│   ├── database.py           # Async SQLAlchemy engine + session
│   ├── redis_client.py       # Redis singleton with queue helpers
│   ├── models/               # 12 SQLAlchemy 2.0 models
│   ├── schemas/              # 12 Pydantic v2 schemas
│   ├── engines/              # Core business logic
│   │   ├── access_control.py # 7-step access pipeline
│   │   ├── credit_engine.py  # Credit operations
│   │   ├── delivery_engine.py# Content delivery + queue
│   │   ├── token_service.py  # Token CRUD + validation
│   │   └── membership_engine.py
│   ├── services/             # Higher-level service layer
│   ├── security/             # Auth, HMAC, rate-limit, anti-abuse
│   ├── api/                  # Route handlers
│   │   ├── endpoints/        # Public API routes
│   │   └── admin/            # Admin-only routes (JWT protected)
│   └── migrations/           # Alembic migrations
├── telegram_gateway/         # aiogram bot manager + handlers
├── workers/                  # Background job consumers
├── admin_ui/                 # React + TypeScript admin panel
├── tests/                    # 12 test modules, async fixtures
├── scripts/                  # CLI utilities
├── docs/                     # Architecture, API, Deployment, Scaling
└── docker-compose.yml        # Full stack orchestration
```

## Environment Variables

| Variable | Required | Example | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `postgresql+asyncpg://...` | Async PostgreSQL connection |
| `REDIS_URL` | Yes | `redis://redis:6379/0` | Redis connection |
| `TELEGRAM_BOTS` | Yes | `bot1:id:token:hmac,...` | Comma-separated bot configs |
| `ADMIN_USERNAME` | Yes | `admin` | Admin login username |
| `ADMIN_PASSWORD` | Yes | `secret` | Admin login password |
| `ADMIN_JWT_SECRET` | Yes | `random-string` | JWT signing key |
| `SECRET_KEY` | Yes | `random-string` | App-level secret |
| `CORS_ORIGINS` | No | `["http://localhost:3000"]` | Allowed CORS origins |
| `LOG_LEVEL` | No | `INFO` | Logging level |

## Testing

```bash
# Run all tests
docker-compose exec backend pytest -v

# Run specific test module
docker-compose exec backend pytest tests/test_access_control.py -v

# Run with coverage
docker-compose exec backend pytest --cov=backend -v
```

Tests use SQLite in-memory database and FakeRedis — no external services required.

### Test Coverage

| Module | Tests | Covers |
|--------|-------|--------|
| `test_access_control` | 11 | Free/credit/VIP/blocked/expired token flows |
| `test_credit_engine` | 12 | Balance, add, deduct, admin-set, history |
| `test_delivery_engine` | 5 | Queue jobs, record delivery, deletion flags |
| `test_token_service` | 12 | Create, validate, expiry, single-use, binding |
| `test_membership_engine` | 8 | Grant, revoke, active check, expiry |
| `test_payment_service` | 6 | Create, verify, credit granting |
| `test_referral_service` | 8 | Invite codes, usage, rewards |
| `test_anti_abuse` | 3 | Fraud detection thresholds |
| `test_rate_limiter` | 4 | Rate limiting, independent keys |
| `test_webhook` | 6 | HMAC validation |
| `test_e2e_flow` | 3 | End-to-end integration |
| `test_workers` | 6 | Queue operations, job formats |

## Scripts

| Script | Description | Usage |
|--------|-------------|-------|
| `seed_db.py` | Populate DB with sample data | `python -m scripts.seed_db` |
| `create_test_pack.py` | Create a content pack + token | `python -m scripts.create_test_pack --title "My Pack"` |
| `create_test_token.py` | Generate an access token | `python -m scripts.create_test_token 1 --single-use` |
| `simulate_webhook.py` | Send a signed test webhook | `python -m scripts.simulate_webhook bot1 123456` |
| `register_webhooks.py` | Register webhooks with Telegram | `python -m scripts.register_webhooks --domain https://...` |

## API Overview

See [docs/API.md](docs/API.md) for complete endpoint reference.

### Public Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/auth/login` | Admin JWT login |
| `POST` | `/webhook/{bot_username}` | Telegram webhook receiver |
| `POST` | `/access/check` | Validate token access |
| `POST` | `/payments/create` | Create payment |
| `POST` | `/payments/verify` | Verify payment |

### Admin Endpoints (JWT Required)

Full CRUD for: users, bots, content-packs, pack-items, tokens, credits, memberships, referrals, analytics.

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | System design, data flow, schema |
| [API Reference](docs/API.md) | All endpoints with request/response examples |
| [Deployment](docs/DEPLOYMENT.md) | Docker, SSL, production setup |
| [Scaling](docs/SCALING.md) | Horizontal scaling, DB optimization, K8s |

## License

MIT