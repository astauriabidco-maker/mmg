# Déploiement MMG

## Préparer l'environnement serveur

1. Copier `.env.example` vers `.env`.
2. Remplacer toutes les valeurs `CHANGE_ME`.
3. Générer un secret applicatif :

```bash
openssl rand -hex 32
```

4. Renseigner au minimum :

- `APP_ENV=production`
- `SECRET_KEY`
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `DATABASE_URL=postgresql://POSTGRES_USER:POSTGRES_PASSWORD@db:5432/POSTGRES_DB`
- `FRONTEND_BASE_URL=https://mmg.example.com`
- `CORS_ORIGINS=https://mmg.example.com`
- `VITE_API_URL=https://api.mmg.example.com`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

5. Vérifier la configuration :

```bash
set -a
. ./.env
set +a
BACKEND_HEALTH_URL=https://api.mmg.example.com/health/ready FRONTEND_HEALTH_URL=https://mmg.example.com/health python scripts/prod_check.py
```

## Lancer avec Docker Compose sur le serveur

Depuis le dossier du projet :

```bash
git pull --ff-only origin main
docker compose up --build -d
docker compose ps
```

Le backend expose :

- `GET /health`
- `GET /health/ready`

Le frontend expose :

- `GET /health`

## Base de données

Le `docker-compose.yml` utilise PostgreSQL. Sauvegarder avant chaque déploiement :

```bash
set -a
. ./.env
set +a
BACKUP_DRIVER=docker-compose scripts/postgres_backup.sh
```

Restaurer un dump dans le PostgreSQL Docker courant :

```bash
set -a
. ./.env
set +a
docker compose stop frontend backend
BACKUP_DRIVER=docker-compose BACKUP_FILE=./backups/mmg-YYYYMMDDHHMMSS.dump scripts/postgres_restore.sh
docker compose up -d
```

Si PostgreSQL est exposé hors Docker et que `pg_dump`/`pg_restore` sont installés sur l'hôte, le mode historique reste disponible :

```bash
DATABASE_URL=postgresql://mmg:...@localhost:5432/mmg BACKUP_DRIVER=host scripts/postgres_backup.sh
BACKUP_FILE=./backups/mmg-YYYYMMDDHHMMSS.dump DATABASE_URL=postgresql://mmg:...@localhost:5432/mmg BACKUP_DRIVER=host scripts/postgres_restore.sh
```

Pour SQLite en développement local :

```bash
python scripts/sqlite_backup.py backup --source ./atelier.db --target-dir ./backups
python scripts/sqlite_backup.py restore --source ./backups/atelier-YYYYMMDDHHMMSS.db --target ./atelier.db
```

Pour les migrations :

```bash
DATABASE_URL=sqlite:///./atelier.db alembic -c backend/alembic.ini upgrade head
```

## Procédure de mise à jour prod

1. Sauvegarder PostgreSQL avec `BACKUP_DRIVER=docker-compose scripts/postgres_backup.sh`.
2. Vérifier que le dump créé existe dans `./backups/`.
3. Mettre à jour le code avec `git pull --ff-only origin main`.
4. Redémarrer avec `docker compose up --build -d`.
5. Vérifier `docker compose ps`.
6. Vérifier `GET /health/ready` côté backend et `GET /health` côté frontend.
7. Lancer l'audit non mutatif contre l'environnement cible.

En cas de déploiement cassé :

```bash
docker compose logs backend --tail=200
docker compose logs db --tail=200
docker compose stop frontend backend
BACKUP_DRIVER=docker-compose BACKUP_FILE=./backups/mmg-YYYYMMDDHHMMSS.dump scripts/postgres_restore.sh
docker compose up -d
```

## Sécurité minimale

- Ne jamais utiliser `ADMIN_PASSWORD=1234` en production.
- Définir `SECRET_KEY` avec une valeur unique.
- Définir `CORS_ORIGINS` uniquement avec les domaines réels.
- Définir `FRONTEND_BASE_URL` avec l'URL publique du frontend.
- Garder `/v2/sales/portal/{token}` public : c'est le portail de signature client.
- Vérifier régulièrement les routes protégées avec `scripts/functional_audit.py`.

## Vérification post-déploiement

```bash
curl -fsS https://api.mmg.example.com/health/ready
curl -fsS https://mmg.example.com/health
```

Puis lancer l'audit fonctionnel contre l'environnement cible si les données de test sont autorisées :

```bash
python scripts/functional_audit.py --api https://api.mmg.example.com --frontend https://mmg.example.com --no-mutate
```
