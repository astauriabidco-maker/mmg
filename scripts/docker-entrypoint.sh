#!/bin/sh
# Entrypoint du conteneur backend MMG.
#
# Rôle : appliquer les migrations Alembic AVANT de lancer l'application.
# En production (APP_ENV=production), Alembic est la seule source de vérité
# du schéma PostgreSQL (create_all est désactivé, cf. backend/main.py) : sans
# migration au démarrage, l'application tournerait sur un schéma obsolète.
#
# Garde-fou voulu : `set -e` fait échouer le démarrage du conteneur si la
# migration échoue — un backend qui démarre sur un schéma non migré est un
# incident silencieux ; un conteneur qui refuse de démarrer est visible
# immédiatement (docker compose ps / logs, healthcheck Coolify KO).
#
# DATABASE_URL est lue depuis l'environnement par backend/alembic/env.py
# (priorité à la variable d'environnement sur alembic.ini).
set -e

echo "[entrypoint] Application des migrations Alembic (upgrade head)..."
alembic -c backend/alembic.ini upgrade head
echo "[entrypoint] Migrations appliquées, démarrage de l'application."

# exec pour que le process applicatif (uvicorn) devienne PID 1 et reçoive
# correctement les signaux (SIGTERM lors de docker stop / redéploiement).
exec "$@"
