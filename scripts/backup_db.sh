#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Database Backup Script for Telegram Content Platform
#
# Dumps the PostgreSQL database, compresses it, and pushes
# to the main GitHub repo under backups/ folder.
#
# Usage:
#   ./scripts/backup_db.sh              # backup + push to GitHub
#   ./scripts/backup_db.sh --local      # backup only (no git push)
#
# Cron (5x daily — every 5 hours):
#   0 1,6,11,16,21 * * * cd /home/ubuntu/telegram-content-platform && ./scripts/backup_db.sh >> /home/ubuntu/telegram-content-platform/data/backup.log 2>&1
# ─────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_DIR}/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="db_backup_${TIMESTAMP}.sql.gz"
KEEP_DAYS=7  # Keep last 7 days of local backups
LOCAL_ONLY="${1:-}"

echo "=== Database Backup: $(date) ==="

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Read DB credentials from .env
DB_USER=$(grep '^POSTGRES_USER=' "${PROJECT_DIR}/.env" | cut -d'=' -f2 | tr -d ' \r')
DB_NAME=$(grep '^POSTGRES_DB=' "${PROJECT_DIR}/.env" | cut -d'=' -f2 | tr -d ' \r')
DB_USER="${DB_USER:-platform}"
DB_NAME="${DB_NAME:-content_platform}"

# Dump the PostgreSQL database from the Docker container, compress it
echo "Dumping database (user=${DB_USER}, db=${DB_NAME})..."
sudo docker compose -f "${PROJECT_DIR}/docker-compose.yml" exec -T db \
    pg_dump -U "$DB_USER" -d "$DB_NAME" --clean --if-exists --no-owner \
    | gzip > "${BACKUP_DIR}/${BACKUP_FILE}"

FILESIZE=$(du -h "${BACKUP_DIR}/${BACKUP_FILE}" | cut -f1)
echo "Backup created: ${BACKUP_FILE} (${FILESIZE})"

# Write status JSON for admin panel
cat > "${BACKUP_DIR}/last_backup.json" << EOF
{"file": "${BACKUP_FILE}", "size": "${FILESIZE}", "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")", "status": "success"}
EOF

# Clean up old backups (keep last KEEP_DAYS days)
echo "Cleaning backups older than ${KEEP_DAYS} days..."
find "$BACKUP_DIR" -name "db_backup_*.sql.gz" -mtime +${KEEP_DAYS} -delete 2>/dev/null || true

REMAINING=$(ls -1 "${BACKUP_DIR}"/db_backup_*.sql.gz 2>/dev/null | wc -l)
echo "Local backups remaining: ${REMAINING}"

# ── Push to GitHub (same repo) ───────────────────────────────
if [ "$LOCAL_ONLY" = "--local" ]; then
    echo "Local-only mode — skipping git push"
else
    echo "Pushing to GitHub..."
    cd "$PROJECT_DIR"

    # Add only the backups directory
    git add backups/ 2>/dev/null || true
    git commit -m "backup: ${TIMESTAMP} (${FILESIZE})" --allow-empty 2>/dev/null || true
    git push origin main 2>/dev/null && echo "Pushed to GitHub successfully" || echo "WARNING: GitHub push failed"

    cd "$PROJECT_DIR"
fi

echo "=== Backup complete ==="
