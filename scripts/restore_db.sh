#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Restore Database from Backup
#
# Usage:
#   ./scripts/restore_db.sh backups/db_backup_20260417_030000.sql.gz
#
# WARNING: This will OVERWRITE the current database!
# ─────────────────────────────────────────────────────────────

set -euo pipefail

if [ $# -eq 0 ]; then
    echo "Usage: $0 <backup_file.sql.gz>"
    echo ""
    echo "Available backups:"
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
    ls -lh "${PROJECT_DIR}/backups/"db_backup_*.sql.gz 2>/dev/null || echo "  No backups found."
    exit 1
fi

BACKUP_PATH="$1"

if [ ! -f "$BACKUP_PATH" ]; then
    echo "ERROR: File not found: $BACKUP_PATH"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Read DB credentials from .env
DB_USER=$(grep '^POSTGRES_USER=' "${PROJECT_DIR}/.env" | cut -d'=' -f2 | tr -d ' \r')
DB_NAME=$(grep '^POSTGRES_DB=' "${PROJECT_DIR}/.env" | cut -d'=' -f2 | tr -d ' \r')
DB_USER="${DB_USER:-platform}"
DB_NAME="${DB_NAME:-content_platform}"

echo "=== Database Restore ==="
echo "Backup file: $BACKUP_PATH"
echo ""
echo "WARNING: This will OVERWRITE the current database!"
read -p "Are you sure? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo "Stopping backend and gateway..."
sudo docker compose -f "${PROJECT_DIR}/docker-compose.yml" stop backend gateway worker

echo "Restoring database..."
gunzip -c "$BACKUP_PATH" | sudo docker compose -f "${PROJECT_DIR}/docker-compose.yml" exec -T db \
    psql -U "$DB_USER" -d "$DB_NAME" --single-transaction

echo "Starting services..."
sudo docker compose -f "${PROJECT_DIR}/docker-compose.yml" up -d backend gateway worker

echo "=== Restore complete ==="
echo "Verify: sudo docker compose logs backend --tail 10"
