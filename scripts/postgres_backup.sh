#!/usr/bin/env sh
set -eu

BACKUP_DRIVER="${BACKUP_DRIVER:-host}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
COMPOSE_SERVICE="${COMPOSE_SERVICE:-db}"
mkdir -p "$BACKUP_DIR"

TARGET="$BACKUP_DIR/mmg-$(date -u +%Y%m%d%H%M%S).dump"

if [ "$BACKUP_DRIVER" = "docker-compose" ]; then
    : "${POSTGRES_DB:?POSTGRES_DB is required}"
    : "${POSTGRES_USER:?POSTGRES_USER is required}"
    docker compose exec -T "$COMPOSE_SERVICE" pg_dump \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        --format=custom \
        > "$TARGET"
else
    : "${DATABASE_URL:?DATABASE_URL is required}"
    pg_dump "$DATABASE_URL" --format=custom --file="$TARGET"
fi

echo "$TARGET"
