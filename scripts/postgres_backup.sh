#!/usr/bin/env sh
set -eu

: "${DATABASE_URL:?DATABASE_URL is required}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"

TARGET="$BACKUP_DIR/mmg-$(date -u +%Y%m%d%H%M%S).dump"
pg_dump "$DATABASE_URL" --format=custom --file="$TARGET"
echo "$TARGET"
