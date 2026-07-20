#!/usr/bin/env bash
# Resynchronise la base de développement SQLite (backend/atelier.db).
#
# Pourquoi : la base dev historique a été créée par `create_all` à l'import du
# module puis patchée à la volée (ensure_schema_compatibility) — sa table
# `alembic_version` est vide et `alembic upgrade head` ne peut pas la
# rattraper proprement. Alembic est désormais la source de vérité unique du
# schéma : on repart donc d'une base vierge migrée.
#
# Ce script :
#   1. sauvegarde backend/atelier.db -> backend/atelier.db.bak-YYYYmmdd-HHMMSS
#   2. supprime backend/atelier.db
#   3. recrée le schéma via `alembic upgrade head`
#   4. crée le compte admin + rôles/permissions via init_db.py
#   5. peuple le jeu de démonstration via scripts/seed_demo.py
#
# Usage (depuis la racine du dépôt) :
#   ./scripts/reset_dev_db.sh
#
# Prérequis : l'environnement virtuel du projet (.venv) avec alembic installé.
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON=".venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    echo "Erreur : $PYTHON introuvable. Créez/activez le venv du projet d'abord." >&2
    exit 1
fi

DB_PATH="backend/atelier.db"

if [ -f "$DB_PATH" ]; then
    BACKUP="${DB_PATH}.bak-$(date +%Y%m%d-%H%M%S)"
    echo "Sauvegarde de $DB_PATH -> $BACKUP"
    cp "$DB_PATH" "$BACKUP"
    echo "Suppression de $DB_PATH"
    rm "$DB_PATH"
else
    echo "Aucune base existante ($DB_PATH), création directe."
fi

echo "Migration du schéma (alembic upgrade head)..."
(
    cd backend
    DATABASE_URL="sqlite:///./atelier.db" "../$PYTHON" -m alembic upgrade head
)

echo "Initialisation (compte admin, rôles, permissions)..."
"$PYTHON" init_db.py

echo "Jeu de données de démonstration..."
"$PYTHON" scripts/seed_demo.py

echo "Terminé. Base dev resynchronisée sur Alembic (head)."
