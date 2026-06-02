#!/usr/bin/env sh
set -eu

: "${BACKUP_FILE:?BACKUP_FILE is required}"
BACKUP_DRIVER="${BACKUP_DRIVER:-host}"
COMPOSE_SERVICE="${COMPOSE_SERVICE:-db}"

if [ "$BACKUP_DRIVER" = "docker-compose" ]; then
    : "${POSTGRES_DB:?POSTGRES_DB is required}"
    : "${POSTGRES_USER:?POSTGRES_USER is required}"
    docker compose exec -T "$COMPOSE_SERVICE" pg_restore \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        --clean \
        --if-exists \
        --no-owner \
        < "$BACKUP_FILE"
else
    : "${DATABASE_URL:?DATABASE_URL is required}"
    pg_restore "$BACKUP_FILE" --dbname="$DATABASE_URL" --clean --if-exists --no-owner
fi
