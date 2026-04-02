# Scaling Guide

Strategies for scaling the Telegram Content Access Platform beyond 100k users.

---

## Architecture Scaling Points

```
                           ┌───────────────┐
                           │  Load Balancer │
                           └──┬──────────┬──┘
                     ┌────────┘          └────────┐
              ┌──────┴──────┐          ┌──────────┴──────┐
              │  Backend ×N │          │  Backend ×N      │
              │  (stateless)│          │  (stateless)     │
              └──────┬──────┘          └──────────┬──────┘
                     │                            │
         ┌───────────┴────────────────────────────┴──┐
         │              Connection Pool               │
         └────────┬──────────────────────┬────────────┘
           ┌──────┴──────┐       ┌───────┴───────┐
           │ PostgreSQL  │       │  Redis Cluster │
           │  Primary    │       │  (3+ nodes)    │
           │  + Replicas │       └───────────────┘
           └─────────────┘
```

The platform is designed for horizontal scaling. Every service is stateless; all state lives in PostgreSQL and Redis.

## 1. Backend API Scaling

### Horizontal Scaling (Docker Compose)

```yaml
services:
  backend:
    deploy:
      replicas: 4
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
```

### Load Balancing

Place Nginx or HAProxy in front of backend replicas:

```nginx
upstream backend {
    least_conn;
    server backend_1:8000;
    server backend_2:8000;
    server backend_3:8000;
    server backend_4:8000;
}
```

### Key Principles
- **Stateless API**: No in-process session state. JWT tokens carry auth context.
- **Async I/O**: FastAPI + asyncpg means a single process handles thousands of concurrent connections.
- **Connection Pooling**: SQLAlchemy async engine uses `pool_size=20, max_overflow=10` by default. Adjust per replica count.

## 2. Worker Scaling

Workers consume Redis queues and are fully independent. Scale linearly.

```yaml
services:
  worker:
    deploy:
      replicas: 8    # Scale based on queue depth
```

### Worker Types

| Worker | Queue | CPU | Memory | Scaling Signal |
|--------|-------|-----|--------|----------------|
| `delivery_worker` | `delivery_queue` | Low | Low | Queue depth > 100 |
| `deletion_worker` | `deletion_queue` | Low | Low | Scheduled (cron-like) |
| `credit_worker` | `credit_queue` | Low | Low | Queue depth > 50 |
| `access_worker` | `access_queue` | Low | Low | Queue depth > 200 |

### Monitoring Queue Depth

```python
import aioredis

redis = aioredis.from_url("redis://redis:6379")
depth = await redis.llen("delivery_queue")
```

Scale workers up when queue depth consistently exceeds thresholds.

## 3. Database Scaling

### Connection Pooling

With N backend replicas × 20 pool connections, ensure PostgreSQL `max_connections` is sufficient:

```
max_connections = (backend_replicas × pool_size) + (worker_replicas × 5) + 20
# Example: (4 × 20) + (8 × 5) + 20 = 140
```

Consider **PgBouncer** for connection multiplexing at scale:

```yaml
services:
  pgbouncer:
    image: edoburu/pgbouncer:latest
    environment:
      DATABASE_URL: postgresql://user:pass@db:5432/content_platform
      MAX_CLIENT_CONN: 500
      DEFAULT_POOL_SIZE: 40
```

### Indexing Strategy

Critical indexes (already in migration):

```sql
-- High-frequency lookups
CREATE INDEX ix_users_telegram_id ON users(telegram_id);
CREATE INDEX ix_tokens_token ON tokens(token);
CREATE INDEX ix_bots_username ON bots(username);
CREATE INDEX ix_credits_user_id ON credits(user_id);
CREATE INDEX ix_memberships_user_id ON memberships(user_id);
CREATE INDEX ix_referrals_invite_code ON referrals(invite_code);

-- Range queries
CREATE INDEX ix_memberships_expires ON memberships(expires_at);
CREATE INDEX ix_tokens_expires ON tokens(expires_at);
```

### Read Replicas

For read-heavy admin analytics, route SELECT queries to replicas:

```python
# Separate engines for read/write
write_engine = create_async_engine(DATABASE_URL)
read_engine = create_async_engine(DATABASE_READ_REPLICA_URL)
```

### Table Partitioning (100k+ scale)

Partition large tables by date:

```sql
-- Partition activity_logs by month
CREATE TABLE activity_logs (
    id SERIAL,
    created_at TIMESTAMP,
    ...
) PARTITION BY RANGE (created_at);

CREATE TABLE activity_logs_2024_01 PARTITION OF activity_logs
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
```

## 4. Redis Scaling

### Single Instance Capacity

A single Redis 7 instance handles ~100k ops/sec. For this platform:
- Rate limiting: ~2 ops per API request
- Queue operations: ~1 op per delivery
- **Single instance supports 50k+ concurrent users easily**

### Redis Cluster (Beyond 200k Users)

```yaml
services:
  redis-1:
    image: redis:7-alpine
    command: redis-server --cluster-enabled yes
  redis-2:
    image: redis:7-alpine
    command: redis-server --cluster-enabled yes
  redis-3:
    image: redis:7-alpine
    command: redis-server --cluster-enabled yes
```

### Cache Strategy

| Data | TTL | Purpose |
|------|-----|---------|
| Rate limit counters | 60s | Anti-abuse |
| Bot config | 300s | Avoid DB lookups |
| User credit balance | 30s | Fast balance checks |
| Pack metadata | 600s | Content listing |

## 5. Telegram Gateway Scaling

### Multi-Bot Architecture

Each bot is a thin forwarder — no processing logic. Multiple bots spread the Telegram API rate limit:

| Bots | Rate Limit | Effective Capacity |
|------|------------|-------------------|
| 1 | 30 msg/sec | ~100k users |
| 3 | 90 msg/sec | ~300k users |
| 10 | 300 msg/sec | ~1M users |

### Webhook vs Polling

- **Webhooks** (current): Telegram pushes updates. Scales with backend replicas.
- **Polling**: Only for development. Does not scale.

## 6. Performance Benchmarks

Expected throughput per backend instance (4 vCPU, 2GB RAM):

| Endpoint | Requests/sec | Avg Latency |
|----------|-------------|-------------|
| `GET /health` | 10,000 | 1ms |
| `POST /webhook/{bot}` | 2,000 | 15ms |
| `POST /access/check` | 3,000 | 10ms |
| `POST /auth/login` | 1,000 | 50ms (bcrypt) |
| Admin analytics | 500 | 30ms |

## 7. Kubernetes Deployment (Production at Scale)

For 500k+ users, migrate to Kubernetes:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
spec:
  replicas: 4
  selector:
    matchLabels:
      app: backend
  template:
    spec:
      containers:
      - name: backend
        image: content-platform-backend:latest
        resources:
          requests:
            cpu: 250m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backend-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backend
  minReplicas: 2
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

## Scaling Checklist

| Users | Action |
|-------|--------|
| 0–10k | Single Docker Compose, 1 backend, 1 worker |
| 10k–50k | 2–3 backend replicas, 2 workers, PgBouncer |
| 50k–100k | 4 backends, 4 workers, read replicas, Redis cache layer |
| 100k–500k | Load balancer, 8+ workers, table partitioning, monitoring |
| 500k+ | Kubernetes, Redis Cluster, multiple DB replicas, CDN |