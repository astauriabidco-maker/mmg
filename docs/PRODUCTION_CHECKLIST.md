# Checklist de premier déploiement production — MMG

Ce document est la **checklist opérationnelle du premier déploiement**. Il
complète [`DEPLOYMENT.md`](DEPLOYMENT.md) (procédures détaillées de
déploiement, sauvegarde et restauration) — lire les deux avant de commencer.

## 1. Variables d'environnement obligatoires

Partir de `.env.example` (copie vers `.env`) et remplacer **toutes** les
valeurs `CHANGE_ME`. Variables bloquantes :

| Variable | Rôle | Contrainte |
|---|---|---|
| `APP_ENV` | Active les garde-fous production | `production` |
| `SECRET_KEY` | Signature des JWT | `openssl rand -hex 32` |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Base PostgreSQL 16 | Mot de passe fort unique |
| `DATABASE_URL` | Connexion SQLAlchemy + Alembic | `postgresql://USER:PASS@db:5432/DB` |
| `CORS_ORIGINS` | Origines frontend autorisées | Domaines réels uniquement ; le backend **refuse de démarrer** en prod avec les valeurs par défaut |
| `FRONTEND_BASE_URL` | URL publique du frontend (liens dans les documents) | `https://…` |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Bootstrap du compte admin | `init_db.py` **refuse** `1234`/`CHANGE_ME*` en prod |
| `VITE_API_URL` | URL de l'API **figée au build** de l'image frontend | Toute modification impose un rebuild du frontend |

Recommandées :

| Variable | Rôle | Défaut / repli |
|---|---|---|
| `NF525_HMAC_KEY` | Clé dédiée au sceau NF525 (facturation) | Repli documenté sur `SECRET_KEY` avec warning au démarrage — définir une clé dédiée en prod (`openssl rand -hex 32`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Durée de vie des JWT | 720 (12 h) |
| `LOGIN_RATE_LIMIT_*` | Réglage du rate limiting `/token` (5 échecs / 10 min par défaut) | Voir `backend/core/rate_limit.py` |

Watcher fichiers (uniquement si le pipeline d'import Proges est activé) :
`WATCH_DIR`, `LABEL_OUTPUT_DIR`, `OUTPUT_QR_DIR`, `API_URL`, `PRINTER_NAME`.

Intégrations optionnelles (laisser vide tant que non utilisées) :
`OPENAI_API_KEY` (fonctions IA), `WHATSAPP_VERIFY_TOKEN` /
`WHATSAPP_ACCESS_TOKEN` / `WHATSAPP_PHONE_ID` / `MANAGER_PHONE` (notifications
WhatsApp), `SMTP_SERVER` / `SMTP_PORT` (watcher fichiers / QR).

Email transactionnel (confirmation de devis signé — `backend/core/events.py`) :

| Variable | Rôle | Défaut / repli |
|---|---|---|
| `SMTP_HOST` | Hôte du serveur SMTP | **Obligatoire** pour activer l'envoi ; absent → emails ignorés (warning log) |
| `SMTP_PORT` | Port SMTP | 587 |
| `SMTP_USER` | Identifiant d'authentification | Vide → pas de `login` |
| `SMTP_PASSWORD` | Mot de passe SMTP | Vide |
| `SMTP_FROM` | Adresse d'expédition | Repli sur `SMTP_USER` ; **obligatoire** (via l'une des deux) |
| `SMTP_USE_TLS` | STARTTLS après connexion | `true` (mettre `false` pour un relais local non chiffré) |
| `CRM_REMINDERS_ENABLED` | Génération autonome des plans de relance | `true` |
| `CRM_REMINDER_SYNC_INTERVAL_SECONDS` | Intervalle du worker backend, en secondes | 300 (minimum 30) |
| `CRM_SMTP_REQUIRED` | Garde-fou SMTP du CRM | `true` ; en production, le backend refuse de démarrer si le worker est actif sans `SMTP_HOST` et `SMTP_FROM`/`SMTP_USER` |

Le worker CRM s'exécute automatiquement à l'intervalle configuré, sans dépendre
de l'ouverture du cockpit. La synchronisation est idempotente en base :
plusieurs passages ne recréent pas les mêmes plans.

## 2. Migrations de schéma — automatiques au déploiement

**Alembic est la seule source de vérité du schéma en production**
(`create_all` y est désactivé, cf. `backend/main.py` et `init_db.py`).

- Au démarrage du conteneur backend, `scripts/docker-entrypoint.sh` exécute
  `alembic upgrade head` **avant** uvicorn (branché via `ENTRYPOINT` dans
  `Dockerfile.backend`).
- Garde-fou voulu : si la migration échoue, le conteneur **ne démarre pas**
  (`set -e`) — visible immédiatement via `docker compose ps` / logs / Coolify.
- Le healthcheck du backend tolère le temps de migration
  (`start_period: 120s` dans `docker-compose.coolify.yml`).
- Avant chaque mise à jour : **sauvegarder PostgreSQL** (cf. §4) — une
  migration qui échoue à mi-chemin se répare depuis un dump, jamais à la main.

## 3. Mots de passe et comptes — première connexion

Le bootstrap crée un seul compte (`ADMIN_USERNAME` / `ADMIN_PASSWORD`).
Des comptes de démonstration peuvent exister si `backend/seed_users.py` ou
`scripts/seed_demo.py` ont été joués (`admin/1234`, `manager/0000`,
`op_debit/1111`, `op_soudure/2222`) : **ils ne doivent jamais rester actifs
en production**.

Procédure après le premier déploiement :

1. Se connecter avec le compte admin bootstrap (`ADMIN_USERNAME`).
2. **Changer immédiatement son mot de passe** : il n'existe pas d'endpoint
   self-service ; le changement se fait par un ADMIN/MANAGER via
   `PUT /v2/config/users/{user_id}` avec `{"pin": "nouveau-mot-de-passe"}`
   (écran de gestion des utilisateurs côté frontend, ou `curl` avec le JWT
   admin). Les rôles opérateurs exigent un PIN à exactement 4 chiffres, les
   autres rôles un mot de passe d'au moins 4 caractères (viser 12+).
3. **Créer les comptes réels** (gérant, vendeurs, opérateurs) via
   `POST /v2/config/users`, avec des secrets forts et uniques.
4. **Désactiver les comptes démo**. Il n'existe pas encore d'endpoint de
   désactivation : passer par la base —
   `docker compose exec db psql -U $POSTGRES_USER -d $POSTGRES_DB -c "UPDATE users SET is_active = false WHERE username IN ('manager','op_debit','op_soudure');"`
   (conserver un seul compte admin actif, dont le mot de passe vient d'être
   changé). La désactivation révoque de fait les JWT existants : chaque
   requête authentifiée revérifie `is_active` en base.
5. Vérifier qu'aucun PIN à 4 chiffres trivial (1234, 0000, 1111…) ne reste
   actif : le rate limiting de `/token` (5 échecs → blocage 10 min par
   IP + identifiant) ralentit la force brute mais ne remplace pas des
   secrets forts.

## 4. Sauvegardes PostgreSQL

⚠️ `scripts/sqlite_backup.py` ne couvre **que SQLite** (développement) — il
ne sauvegarde rien en production.

- Sauvegarde manuelle avant chaque intervention (détaillée dans
  `DEPLOYMENT.md`) : `BACKUP_DRIVER=docker-compose scripts/postgres_backup.sh`.
- Mettre en place une **tâche cron externe** (hôte ou service de backup) qui
  exécute `postgres_backup.sh` quotidiennement et **externalise** les dumps
  (`./backups/*.dump`) hors du serveur (S3, NAS, etc.) :

  ```cron
  17 3 * * * cd /srv/mmg && set -a && . ./.env && set +a && BACKUP_DRIVER=docker-compose scripts/postgres_backup.sh && rsync -a ./backups/ backup-user@nas:/backups/mmg/
  ```

- Tester une restauration (`scripts/postgres_restore.sh`) au moins une fois
  avant l'ouverture réelle du service.

## 5. HTTPS / reverse proxy

- Le stack Docker expose le frontend (port 80 du conteneur) et le backend
  (port 7000) : les placer derrière un reverse proxy TLS (Traefik de Coolify,
  nginx, Caddy…) avec certificats Let's Encrypt.
- `CORS_ORIGINS`, `FRONTEND_BASE_URL` et `VITE_API_URL` doivent utiliser les
  URL **publiques en HTTPS** ; `VITE_API_URL` exige un rebuild du frontend.
- Garder `/v2/sales/portal/{token}` public (portail de signature client).

## 6. Fonctionnalités à activer progressivement

Ne pas tout activer le jour J. Ordre conseillé :

1. **Socle** (comptes, devis, stock) : utilisable dès la checklist ci-dessus
   validée.
2. **POS / facturation NF525** : définir `NF525_HMAC_KEY` **avant** la
   première facture (la chaîne de scellés dépend de la clé ; la changer après
   coup invalide la vérification de la chaîne existante).
3. **Logistique / watcher fichiers** : monter les volumes `WATCH_DIR` /
   `LABEL_OUTPUT_DIR` / `OUTPUT_QR_DIR` et vérifier les droits avant d'activer
   le pipeline d'import.
4. **WhatsApp** : nécessite les 4 variables `WHATSAPP_*` + `MANAGER_PHONE` ;
   sans elles les notifications sont simplement journalisées.
5. **IA** : nécessite `OPENAI_API_KEY` ; sans clé, les fonctions IA sont
   inactives.
6. **Email SMTP** : emails transactionnels réels (confirmation de devis signé,
   portail client, passage « Accepté » et relances CRM). Nécessite `SMTP_HOST`
   et `SMTP_FROM` (voir §1). Avec les relances CRM actives en production, ces
   variables sont bloquantes au démarrage afin d'éviter des relances seulement
   journalisées. L'écran
   « Paramètres plateforme → Tester SMTP » permet de valider les identifiants
   avant de les poser dans `.env`.

## 7. Vérifications finales avant ouverture

- [ ] `docker compose ps` : `db`, `backend`, `frontend` healthy
- [ ] `curl -fsS https://api.<domaine>/health/ready` → `{"status":"ready"}`
- [ ] `python scripts/prod_check.py` (voir `DEPLOYMENT.md`)
- [ ] Connexion admin OK, mot de passe changé, comptes démo désactivés
- [ ] 6 tentatives de login avec un mauvais PIN → HTTP 429
- [ ] Un utilisateur sans `SALES_EDIT` reçoit HTTP 403 sur les écritures CRM
- [ ] `CRM_REMINDERS_ENABLED=true`, SMTP testé et worker visible dans les logs
- [ ] `cd frontend_v2 && npm run test:e2e` → parcours CRM Playwright vert
- [ ] Import/export CSV client, segmentation, contacts et fusion de doublons testés
- [ ] Sauvegarde cron en place + une restauration testée
- [ ] `NF525_HMAC_KEY` défini (si POS activé)
- [ ] Audit non mutatif : `python scripts/functional_audit.py --api https://api.<domaine> --frontend https://<domaine> --no-mutate`
