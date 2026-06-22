# Déploiement Coolify MMG

Ce guide utilise `docker-compose.coolify.yml`, prévu pour Coolify :

- pas de mapping `ports:` direct sur le serveur ;
- PostgreSQL reste privé ;
- Coolify expose `frontend` et `backend` via son proxy ;
- les variables critiques sont marquées obligatoires avec la syntaxe Compose `${VAR:?}`.

## 1. Préparer les domaines

Prévoir deux domaines ou sous-domaines :

- frontend : `https://mmg.example.com`
- backend API : `https://api.mmg.example.com`

Pointer les DNS vers le serveur Coolify avant le déploiement.

## 2. Créer l'application Coolify

1. Dans Coolify, créer une nouvelle application depuis le dépôt GitHub.
2. Choisir le build pack `Docker Compose`.
3. Utiliser le fichier Compose `docker-compose.coolify.yml`.
4. Ne pas utiliser le mode `Raw Compose Deployment`, sauf besoin avancé.

## 3. Configurer les domaines Coolify

Dans la liste des services détectés :

- service `frontend` : assigner `https://mmg.example.com`
- service `backend` : assigner `https://api.mmg.example.com:7000`
- service `db` : ne pas assigner de domaine

Le `:7000` du domaine backend indique à Coolify le port interne du conteneur backend. Le proxy publie quand même le service en HTTPS standard.

## 4. Variables d'environnement

Dans Coolify, utiliser la vue développeur des variables et renseigner :

```env
APP_ENV=production
SECRET_KEY=CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32
ACCESS_TOKEN_EXPIRE_MINUTES=720

POSTGRES_DB=mmg
POSTGRES_USER=mmg
POSTGRES_PASSWORD=CHANGE_ME_STRONG_DATABASE_PASSWORD

FRONTEND_BASE_URL=https://mmg.example.com
CORS_ORIGINS=https://mmg.example.com
VITE_API_URL=https://api.mmg.example.com

ADMIN_USERNAME=admin
ADMIN_PASSWORD=CHANGE_ME_STRONG_ADMIN_PASSWORD

OPENAI_API_KEY=
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_ID=
MANAGER_PHONE=

LABEL_OUTPUT_DIR=/data/output/labels
WATCH_DIR=/data/exports_proges_valides
OUTPUT_QR_DIR=/data/output/qr
API_URL=http://backend:7000
PRINTER_NAME=
SMTP_SERVER=localhost
SMTP_PORT=1025
```

Générer `SECRET_KEY` :

```bash
openssl rand -hex 32
```

Ne jamais garder `ADMIN_PASSWORD=1234` en production.

Ne pas créer de variable `DATABASE_URL` dans Coolify pour ce Compose.
`docker-compose.coolify.yml` la construit automatiquement avec le host interne `db`.
Si une ancienne variable `DATABASE_URL` existe et pointe vers un host généré par Coolify, la supprimer ou l'ignorer.

Si les logs affichent `Can't load plugin: sqlalchemy.dialects:postgres`, la variable `DATABASE_URL` commence par `postgres://`.
Remplacer par `postgresql://` :

```env
DATABASE_URL=postgresql://mmg:CHANGE_ME_STRONG_DATABASE_PASSWORD@db:5432/mmg
```

## 5. Déployer

1. Lancer le déploiement dans Coolify.
2. Vérifier que les trois services sont `healthy` :
   - `db`
   - `backend`
   - `frontend`
3. Vérifier les URLs :

```bash
curl -fsS https://api.mmg.example.com/health/ready
curl -fsS https://mmg.example.com/health
```

4. Lancer un audit non mutatif depuis une machine qui peut joindre les domaines :

```bash
python scripts/functional_audit.py \
  --api https://api.mmg.example.com \
  --frontend https://mmg.example.com \
  --username admin \
  --password CHANGE_ME_STRONG_ADMIN_PASSWORD \
  --no-mutate
```

## 6. Sauvegarder PostgreSQL sur Coolify

Dans le terminal Coolify ou via SSH dans le dossier de l'application :

```bash
set -a
. ./.env
set +a
BACKUP_DRIVER=docker-compose scripts/postgres_backup.sh
```

Les dumps sont créés dans `./backups/`.

## 7. Restaurer PostgreSQL sur Coolify

Couper l'application avant de restaurer :

```bash
set -a
. ./.env
set +a
docker compose stop frontend backend
BACKUP_DRIVER=docker-compose BACKUP_FILE=./backups/mmg-YYYYMMDDHHMMSS.dump scripts/postgres_restore.sh
docker compose up -d
```

Après restauration, vérifier :

```bash
docker compose ps
curl -fsS https://api.mmg.example.com/health/ready
curl -fsS https://mmg.example.com/health
```

## 8. Points de vigilance

- `VITE_API_URL` est une variable de build frontend : si elle change, redéployer/rebuilder le frontend.
- `DATABASE_URL` est générée par le Compose avec le host Docker `db`, pas `localhost` ni un identifiant Coolify.
- Ne pas exposer PostgreSQL avec un domaine ou un port public.
- Garder `CORS_ORIGINS` limité au domaine frontend réel.
- Si Coolify affiche "No available server" sur l'API, vérifier que le domaine backend cible bien `:7000`.
- Si le déploiement échoue avec `backend is unhealthy`, ouvrir les logs du service `backend`.
  Le backend exécute les migrations et `init_db.py` avant de lancer l'API ; le premier démarrage peut prendre plus longtemps qu'un redéploiement classique.
