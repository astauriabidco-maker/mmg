#!/usr/bin/env sh
set -eu

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_FILE:?BACKUP_FILE is required}"

pg_restore "$BACKUP_FILE" --dbname="$DATABASE_URL" --clean --if-exists
