# Déploiement MMG

## Préparer l'environnement

1. Copier `.env.example` vers `.env`.
2. Remplacer toutes les valeurs `CHANGE_ME`.
3. Générer un secret applicatif :

```bash
openssl rand -hex 32
```

4. Vérifier la configuration :

```bash
APP_ENV=production SECRET_KEY=... ADMIN_PASSWORD=... DATABASE_URL=sqlite:///./atelier.db FRONTEND_BASE_URL=https://mmg.example.com CORS_ORIGINS=https://mmg.example.com scripts/prod_check.py
```

## Lancer avec Docker Compose

```bash
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
DATABASE_URL=postgresql://mmg:...@localhost:5432/mmg scripts/postgres_backup.sh
BACKUP_FILE=./backups/mmg-YYYYMMDDHHMMSS.dump DATABASE_URL=postgresql://mmg:...@localhost:5432/mmg scripts/postgres_restore.sh
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
