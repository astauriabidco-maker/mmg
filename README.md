# MMG — Gestion d'atelier de menuiserie (mini-ERP)

Application de gestion complète pour un atelier de fabrication de menuiseries
(PVC / ALU) : de la prise de mesures sur chantier jusqu'à la facturation, en
passant par la production, le stock et la logistique.

## Périmètre fonctionnel

- **Production atelier** : file d'attente par poste (planning), démarrage /
  pause / arrêt des tâches par les opérateurs, suivi temps réel (WebSocket),
  journal de production par poste et par commande.
- **Import des débits** : import des fichiers de débits atelier
  (Progers / Orgadata, PDF et TXT) via l'endpoint d'ingestion ; extraction et
  création automatique des ordres de fabrication.
- **Stock double-entrée** : catalogue produits et variantes (PIM), emplacements
  arborescents, quants par emplacement, mouvements valorisés (achats,
  consommation atelier, livraisons, ajustements), réservations atelier,
  inventaires physiques.
- **Ventes (CRM B2B)** : clients, devis multi-lignes, portail client de
  signature électronique (lien signé par token), conversion devis → ordres de
  fabrication → livraison → facture.
- **Dossiers MMG** : prise de mesures sur chantier (Métré Menuiserie Générale)
  avec paramètres techniques complets (ouverture, vitrage, quincaillerie,
  accessibilité), photos et signature, lien vers les devis et la production.
- **Achats** : fournisseurs enrichis (incoterms, délais, conditions de
  paiement), commandes fournisseurs, réceptions partielles ou totales,
  factures fournisseurs et rapprochement.
- **Facturation** : factures clients (acompte, solde, avoir), paiements,
  conformité NF525 (scellement chaîné des pièces).
- **POS (B2C)** : sessions de caisse, tickets, mouvements de fonds de caisse.
- **Logistique** : tournées de livraison, bons de livraison, application
  chauffeur.
- **RBAC** : rôles (SUPER_ADMIN, ADMIN, MANAGER, SALES, OPERATOR,
  DEBIT_OPERATOR, QUALITY_CONTROLLER, WORKSHOP_LEAD) et permissions fines par
  module (comptabilité, ventes, stocks, atelier).
- **Intégrations optionnelles** : notifications WhatsApp, assistance IA
  (OpenAI), impression d'étiquettes Zebra (QR codes).

## Stack technique

| Couche | Technologie |
| :--- | :--- |
| Backend | Python 3, FastAPI, SQLAlchemy, Alembic, JWT (python-jose), passlib (pbkdf2_sha256) |
| Frontend | React 18, Vite, Tailwind CSS, React Query, Recharts, react-signature-canvas |
| Base de données | PostgreSQL 16 en production, SQLite (`atelier.db`) en développement |
| Déploiement | Docker / Docker Compose, Coolify |

## Architecture du dépôt

```
backend/            API FastAPI (routers v2, modèles SQLAlchemy, migrations Alembic)
frontend_v2/        Application React (interface manager, opérateur, POS, portail client)
android_app/        Application Android native (Kotlin) — legacy, non déployée
scripts/            Scripts d'exploitation (imports réels, sauvegardes, contrôles prod)
scripts/legacy/     watcher / surveillance / extractor — services de surveillance de
                    dossiers utilisables manuellement (hors déploiement Docker)
tests/              Suite de tests pytest (backend + flux métier)
docs/               Documentation exploitation (déploiement, imports)
docs/archive/       Historique du projet (plans d'implémentation, walkthroughs)
init_db.py          Bootstrap de la base et du compte admin (référencé par Docker)
uploads/            Fichiers importés (servis sur /uploads)
```

## Démarrage en développement

Prérequis : Python 3.11+, Node 18+.

```bash
# Backend (port 7000)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python init_db.py                      # crée les tables et le compte admin
python -m uvicorn backend.main:app --reload --port 7000

# Frontend (port 5000, proxy /api et /ws vers le backend)
cd frontend_v2
npm install
npm run dev
```

L'interface est accessible sur http://localhost:5000, l'API sur
http://localhost:7000 (documentation OpenAPI : `/docs`).

### Données de démonstration

```bash
python scripts/seed_demo.py
```

Peuple la base de développement avec un jeu réaliste et idempotent :
utilisateurs par rôle, clients, fournisseurs, catalogue + stock, un devis
signé suivi jusqu'à la facture, une commande fournisseur réceptionnée et un
dossier MMG. Les mots de passe sont configurables via les variables
`DEMO_*_PASSWORD` (défauts de dev documentés dans le script).

### Gestion du schéma (Alembic)

Alembic est la **source de vérité unique** du schéma, en dev comme en prod :

- `cd backend && alembic upgrade head` applique les migrations
  (`DATABASE_URL` prioritaire sur la valeur de `alembic.ini`).
- Au démarrage, l'application n'écrit **rien** en base à l'import du module :
  le lifespan FastAPI exécute uniquement les seeds de référence (stations,
  rôles/permissions) et, **hors production seulement**, un
  `create_all` idempotent en filet de sécurité dev. En production
  (`APP_ENV=production`), un schéma non migré fait échouer le démarrage :
  lancer `alembic upgrade head` avant.

**Resynchroniser la base dev historique.** Les bases `atelier.db` créées avant
cette unification ont dérivé (table `alembic_version` vide, colonnes patchées
à la volée) et ne peuvent pas être rattrapées par `alembic upgrade head`.
La procédure de remise à neuf (sauvegarde incluse) :

```bash
./scripts/reset_dev_db.sh
```

Le script sauvegarde `backend/atelier.db` (`atelier.db.bak-<horodatage>`), la
supprime, puis la recrée via `alembic upgrade head` + `init_db.py` +
`scripts/seed_demo.py`.

### Variables d'environnement clés

| Variable | Rôle | Défaut dev |
| :--- | :--- | :--- |
| `DATABASE_URL` | Connexion DB (`sqlite:///./atelier.db` ou `postgresql://…`) | `sqlite:///./atelier.db` |
| `SECRET_KEY` | Signature des JWT | secret de dev intégré |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Bootstrap du compte admin par `init_db.py` | `admin` / `1234` |
| `APP_ENV` | `development` ou `production` | `development` |
| `CORS_ORIGINS` | Origines autorisées | localhost:5000/5173/7000 |
| `OPENAI_API_KEY`, `WHATSAPP_*` | Intégrations optionnelles | désactivées |
| `CRM_REMINDERS_ENABLED` | Worker autonome de génération des relances CRM | `true` |
| `CRM_REMINDER_SYNC_INTERVAL_SECONDS` | Fréquence du worker CRM | `300` |
| `CRM_SMTP_REQUIRED` | Refuse le démarrage production sans SMTP quand les relances sont actives | `true` |

**Garde-fous production** (`APP_ENV=production`) : le démarrage **refuse** un
`SECRET_KEY` par défaut, un `ADMIN_PASSWORD` par défaut (`1234` ou
`CHANGE_ME…`) ou des `CORS_ORIGINS` non explicités.

## Tests

```bash
python -m pytest tests/ -q
cd frontend_v2
npm run build
npm run test:e2e
```

Couvre : santé de l'API, flux de production, flux ventes/signature, achats et
stock, inventaires, dossiers MMG, compatibilité de schéma, durcissement
sécurité, numérotation/scellement NF525, RBAC et fonctions CRM avancées. Le
test Playwright simule les API de façon déterministe et vérifie dans un vrai
navigateur le parcours client → contact → opportunité → fusion de doublon.

## Déploiement (Docker / Coolify)

Voir `docs/DEPLOYMENT.md` et `docs/COOLIFY.md` pour le détail. En résumé :

```bash
cp .env.example .env   # remplacer tous les CHANGE_ME
docker compose up --build -d
```

Le conteneur backend exécute `alembic upgrade head`, puis `init_db.py`, puis
démarre uvicorn sur le port 7000. Le frontend est buildé en statique et servi
par nginx (port 5000). `scripts/prod_check.py` valide la configuration avant
mise en production. `docker-compose.coolify.yml` est la variante pour Coolify.

## Legacy / archivé

- `scripts/legacy/` : `watcher.py`, `surveillance.py`, `extractor.py` —
  services de surveillance de dossiers (import automatique de débits PDF,
  génération de QR codes) utilisés avant l'endpoint d'ingestion `/v2/ingest`.
  Ils ne sont lancés par aucun déploiement mais restent exécutables
  manuellement, par exemple : `python scripts/legacy/watcher.py`.
- `android_app/` : application Android Kotlin de la V1 (scan opérateur) —
  conservée à titre de référence, non maintenue.
- `docs/archive/` : plans d'implémentation, walkthroughs et rapports de
  validation des phases précédentes du projet.
- Supprimés lors du chantier d'hygiène : frontend React v1 (build non monté,
  endpoint `/dashboard/metrics` inexistant), prototype mobile Flutter,
  screenshots de debug, artefacts d'agent (`*.md.resolved*`,
  `*.metadata.json`), tests et scripts one-shot racine.
