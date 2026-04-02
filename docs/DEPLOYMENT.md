# Deployment Guide

## Oracle Cloud Free Tier (Recommended — $0/month, everything in one place)

Oracle Always Free gives a **permanent** ARM VM: **4 OCPUs + 24GB RAM** — more than
enough for 500–1K users. Everything runs via Docker Compose on a single machine.

### Step 1 — Create Oracle Cloud VM

1. Sign up at https://cloud.oracle.com (credit card for verification only — never charged)
2. Compute → Create Instance:
   - Shape: **VM.Standard.A1.Flex** → 4 OCPUs, 24 GB RAM *(Ampere ARM, always-free)*
   - Image: **Ubuntu 22.04**
   - Paste in your SSH public key
3. In your VCN security list, open ingress for ports **22, 80, 443**
4. Note the public IP

### Step 2 — Install Docker

```bash
ssh ubuntu@YOUR_VM_IP
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker ubuntu && newgrp docker
```

### Step 3 — Point a Domain

Add a DNS A record: `yourdomain.com → YOUR_VM_IP`

### Step 4 — Clone & Configure

```bash
git clone https://github.com/YOUR_ORG/YOUR_REPO.git
cd YOUR_REPO
cp .env.example .env
nano .env
```

Key values to fill in:

```env
# DB — uses the local Docker postgres, no external service needed
DATABASE_URL=postgresql+asyncpg://platform:STRONGPASS@db:5432/content_platform
DATABASE_URL_SYNC=postgresql://platform:STRONGPASS@db:5432/content_platform
POSTGRES_DB=content_platform
POSTGRES_USER=platform
POSTGRES_PASSWORD=STRONGPASS

# Redis — uses the local Docker redis, no external service needed
REDIS_URL=redis://redis:6379/0

# Generate with: python3 -c "import secrets; print(secrets.token_urlsafe(48))"
SECRET_KEY=GENERATE_THIS
ADMIN_JWT_SECRET=GENERATE_THIS
INTERNAL_API_KEY=GENERATE_THIS

ADMIN_USERNAME=admin
ADMIN_PASSWORD=STRONG_PASSWORD

# Format: username:token:hmac_secret
TELEGRAM_BOTS=mybot:123456789:ABCdefSecret

# Admin UI API routing (baked into the JS bundle at build time)
VITE_API_BASE_URL=https://yourdomain.com/api

CORS_ORIGINS=["https://yourdomain.com"]
DEBUG=false
LOG_LEVEL=INFO
WORKER_POLL_INTERVAL=1.0
```

### Step 5 — Set Nginx Domain

```bash
sed -i 's/YOUR_DOMAIN/yourdomain.com/g' nginx/nginx.conf
```

### Step 6 — Issue SSL Certificate (Let's Encrypt — free)

```bash
# Start nginx temporarily with HTTP-only dev config for ACME challenge:
cp nginx/nginx.conf nginx/nginx.conf.bak
cp nginx/nginx.dev.conf nginx/nginx.conf
docker compose up -d nginx

# Issue certificate:
docker compose --profile certbot run --rm certbot certonly \
  --webroot --webroot-path=/var/www/certbot \
  -d yourdomain.com --email you@email.com --agree-tos --no-eff-email

# Restore HTTPS config:
cp nginx/nginx.conf.bak nginx/nginx.conf
docker compose restart nginx
```

### Step 7 — Migrate Database & Launch

```bash
docker compose up -d db redis          # start DB + Redis first
docker compose run --rm backend alembic upgrade head   # run migrations
docker compose up -d                   # start everything
```

### Step 8 — Register Telegram Webhooks

```bash
docker compose exec backend python scripts/register_webhooks.py --domain https://yourdomain.com
```

### Step 9 — Verify

- Admin panel: `https://yourdomain.com`
- API health: `https://yourdomain.com/api/health`

### SSL Auto-Renewal (cron)

```bash
crontab -e
# Add:
0 3 * * * cd /home/ubuntu/YOUR_REPO && docker compose --profile certbot run --rm certbot renew --quiet && docker compose restart nginx
```

### Updating

```bash
git pull
docker compose build
docker compose up -d
docker compose run --rm backend alembic upgrade head   # if schema changed
```

---



- Docker 24+ and Docker Compose v2+
- A server with at least 2GB RAM
- Public domain with SSL certificate (for Telegram webhooks)
- Telegram Bot API tokens (create via [@BotFather](https://t.me/BotFather))

## Quick Start (Development)

```bash
# 1. Clone the repository
git clone <repository-url>
cd telegram-content-platform

# 2. Create environment file
cp .env.example .env

# 3. Edit .env with your settings
#    At minimum, set:
#    - TELEGRAM_BOTS=botname:123456:BOT_TOKEN:hmac_secret
#    - ADMIN_PASSWORD=your-secure-password
#    - ADMIN_JWT_SECRET=random-32-char-string

# 4. Start all services
docker-compose up --build

# 5. Run database migrations
docker-compose exec backend alembic upgrade head

# 6. Seed sample data (optional)
docker-compose exec backend python -m scripts.seed_db

# 7. Access services:
#    Backend API:  http://localhost:8000
#    Admin Panel:  http://localhost:3000
#    Health check: http://localhost:8000/health
```

## Production Deployment

### 1. Environment Configuration

```bash
cp .env.example .env
```

Critical production settings:

```env
# Security — CHANGE ALL OF THESE
SECRET_KEY=<random-64-char-string>
ADMIN_PASSWORD=<bcrypt-hash-of-your-password>
ADMIN_JWT_SECRET=<random-64-char-string>

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@db-host:5432/content_platform
DATABASE_URL_SYNC=postgresql://user:pass@db-host:5432/content_platform

# Redis
REDIS_URL=redis://redis-host:6379/0

# Telegram Bots (comma-separated: username:token:hmac_secret)
TELEGRAM_BOTS=bot1:123:ABC:secret1,bot2:456:DEF:secret2

# CORS (restrict to your domain)
CORS_ORIGINS=["https://admin.yourdomain.com"]

# Debug OFF
DEBUG=False
LOG_LEVEL=WARNING
```

### 2. SSL/HTTPS Setup

Telegram requires HTTPS for webhook URLs. Options:

**Option A: Nginx Reverse Proxy (Recommended)**
```nginx
server {
    listen 443 ssl;
    server_name api.yourdomain.com;
    
    ssl_certificate /etc/ssl/cert.pem;
    ssl_certificate_key /etc/ssl/key.pem;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

server {
    listen 443 ssl;
    server_name admin.yourdomain.com;
    
    ssl_certificate /etc/ssl/cert.pem;
    ssl_certificate_key /etc/ssl/key.pem;
    
    location / {
        proxy_pass http://localhost:3000;
    }
}
```

**Option B: Cloudflare Tunnel**
```bash
cloudflared tunnel --url http://localhost:8000
```

### 3. Register Telegram Webhooks

```bash
python scripts/register_webhooks.py --domain https://api.yourdomain.com
```

### 4. Database Migrations

```bash
# Initial migration
docker-compose exec backend alembic upgrade head

# Create new migration after model changes
docker-compose exec backend alembic revision --autogenerate -m "description"
docker-compose exec backend alembic upgrade head
```

### 5. Docker Compose Production Overrides

Create `docker-compose.prod.yml`:

```yaml
services:
  backend:
    restart: always
    environment:
      - DEBUG=False
    deploy:
      resources:
        limits:
          memory: 512M
    
  worker:
    restart: always
    deploy:
      replicas: 3
      resources:
        limits:
          memory: 256M
    
  db:
    volumes:
      - pgdata:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          memory: 1G

volumes:
  pgdata:
```

Run with:
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Monitoring

### Health Checks

```bash
# API health
curl http://localhost:8000/health

# Docker service status
docker-compose ps

# Container logs
docker-compose logs -f backend
docker-compose logs -f worker
```

### Database Backups

```bash
# Backup
docker-compose exec db pg_dump -U platform content_platform > backup_$(date +%Y%m%d).sql

# Restore
cat backup.sql | docker-compose exec -T db psql -U platform content_platform
```

## Updating

```bash
# Pull latest changes
git pull

# Rebuild and restart
docker-compose down
docker-compose up --build -d

# Run any new migrations
docker-compose exec backend alembic upgrade head
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Backend won't start | Check `DATABASE_URL` and ensure PostgreSQL is healthy |
| Redis connection error | Verify `REDIS_URL` and Redis container status |
| Webhook 403 errors | Check HMAC secrets match between `.env` and bots |
| Admin login fails | Verify `ADMIN_USERNAME` / `ADMIN_PASSWORD` in `.env` |
| Workers not processing | Check `WORKER_TYPE` env var, verify Redis connectivity |
| Migration errors | Run `alembic downgrade -1` then `alembic upgrade head` |