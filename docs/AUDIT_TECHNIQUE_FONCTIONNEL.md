# Audit technique & fonctionnel — Projet MMG

**Date :** 2026-07-19
**Périmètre :** backend FastAPI, frontend_v2 (React), frontend v1, mobile Flutter, android_app Kotlin, base SQLite, Docker/Coolify, documentation.
**Vérifications exécutées :** `pytest tests/` → **49/49 tests verts**, `alembic heads` → chaîne linéaire saine (tête `7c9d1e4a5b28`).

---

## 1. Vision d'ensemble

Le projet a démarré comme un **suivi de production d'atelier de menuiserie ALU/PVC** (débit, soudure, assemblage, vitrage, contrôle) avec scan QR et import OCR de plans. Il a dérivé vers un **mini-ERP complet** : CRM/devis avec signature client en ligne, portail client, dossiers techniques MMG, stock double-entrée "à la Odoo", achats fournisseurs, facturation NF525, POS, logistique, RBAC 10 rôles, copilote IA de devis, WhatsApp.

**Verdict global :** le cœur atelier (production + débits + stock) est mature, testé et documenté. La couche ERP (ventes/achats/compta/POS/logistique) est largement écrite mais jamais éprouvée avec de vraies données. La surface de sécurité publique présente des lacunes sérieuses à corriger avant toute mise en production réelle. La documentation décrit encore le produit d'il y a quatre sprints.

---

## 2. Points forts

1. **Architecture backend propre** : FastAPI, 17 routers, services dédiés au stock, SQLAlchemy, Pydantic v2, Alembic.
2. **RBAC réel** : 10 rôles, 27 permissions seedées, contrôles `require_roles`/`require_permissions`.
3. **Garde-fous production** : refus de démarrer si `SECRET_KEY`, `CORS_ORIGINS` ou `ADMIN_PASSWORD` par défaut.
4. **Tests d'intégration sérieux** : 49 tests verts, isolation SQLite mémoire, dont un test vérifiant que les routes sensibles exigent l'authentification.
5. **Service stock double-entrée rigoureux** : validation, verrous d'inventaire, traçabilité complète.
6. **Import débits atelier** (TXT Progers + PDF Orgadata) : complet, documenté (`docs/WORKSHOP_DEBITS_IMPORT.md`), testé.
7. **frontend_v2** : couche API centralisée (axios + intercepteur 401), routing lazy, routes protégées par rôle, React Query, PWA.
8. **Docker Coolify** bien ficelé : secrets obligatoires, healthchecks, PostgreSQL 16.

---

## 3. Problèmes critiques (🔴 — à corriger avant toute prod)

| # | Constat | Preuve |
|---|---------|--------|
| C1 | **PDF commerciaux sans authentification (IDOR)** : devis, factures, BL téléchargeables par ID séquentiel sans token → fuite de données clients/financières par énumération. | `backend/routers/v2_pdf.py:16` (router sans `dependencies`), endpoints `:57`, `:215`, `:354` |
| C2 | **PINs/identifiants en dur dans le bundle JS** : table PIN→username (1111→op_debit … 1234→admin, 0000→manager) compilée dans le frontend, correspondant exactement aux comptes seedés. Accès admin trivial si les seeds existent en prod. | `frontend_v2/src/pages/Login.jsx:36-41` ↔ `backend/seed_users.py:29-32` |
| C3 | **JWT jamais revérifié en base** : utilisateur supprimé/désactivé garde l'accès jusqu'à expiration ; durée par défaut **3 000 min (50 h)** ; rôle/permissions figés à l'émission. | `backend/core/security.py:42-50`, `:14` |
| C4 | **Endpoints d'écriture sans auth** : `POST /orders/` crée une commande sans contrôle ; WebSocket `/ws/{client_id}` ouvert à tous. | `backend/main.py:123-131`, `:111-120` |
| C5 | **Page « Dossiers MMG » entièrement cassée** : 5 appels frontend vers des routes inexistantes (404) — `/mmg/list`, `/mmg/submit`, `/mmg/{id}`, mauvaise méthode pour le statut. | `frontend_v2/src/pages/MMGDossiers.jsx:108-256` vs `backend/routers/v2_mmg.py` |
| C6 | **Photos/signatures MMG jamais servies** : écrites sous `backend/static/mmg/` mais `/static` n'est pas monté (seul `/uploads` l'est) → 404 à l'affichage ; perdues au redéploiement Docker. | `backend/routers/v2_mmg.py:26-33` vs `backend/main.py:80` |

---

## 4. Problèmes majeurs (🟠)

### Sécurité
- **M1 — Uploads non validés** : n'importe quelle extension (`.html`, `.svg` → XSS stocké), aucune limite de taille. (`v2_stock.py:531-546`, `v2_ingest.py:74-95`)
- **M2 — Webhook WhatsApp non sécurisé** : token en dur `"mmg_secure_token_123"`, signature `X-Hub-Signature-256` non vérifiée. (`v2_webhook.py:14`, `:34-74`)
- **M3 — JWT + rôle en `localStorage`**, pas de refresh token ; fallback API `http://localhost:7000` compilé dans le bundle prod ; Android en HTTP clair avec URL émulateur en dur et token en mémoire. (`api.js:3,10`, `NetworkModule.kt:11,18`)
- **M4 — Sceau "NF525" factice** : SHA-256 sans clé secrète, incluant le statut mutable, sans chaînage → recalculable par quiconque. Fausse impression de conformité. (`v2_accounting.py:33-36`)
- **M5 — Pas de rate limiting** sur `/token` alors que les opérateurs utilisent des PIN à 4 chiffres.
- **M6 — Path traversal authentifié** : `client_name` utilisé tel quel pour créer un dossier. (`core/events.py:54-59`)

### Dette technique
- **M7 — Numérotation des documents par `COUNT+1`** : race condition sous concurrence + non conforme NF525. (`v2_accounting.py:22-31`, `v2_purchases.py`, `v2_sales.py:312`)
- **M8 — Triple gestion du schéma** : Alembic + `create_all` au démarrage + `ensure_schema_compatibility` (ALTER en dur) ; la table `alembic_version` est absente de `atelier.db` → migrations non appliquées en local ; migration `7c9d1e4a5b28` non commitée (dirty). (`models.py:8-79`, `main.py:18-19`)
- **M9 — Effets de bord à l'import** : `create_all` + seeds exécutés à l'import du module → les tests écrivent dans la vraie DB. (`main.py:18-24`)
- **M10 — Double API fournisseurs** : `/v2/partners/suppliers` (utilisée partout) et `/v2/suppliers` (code mort au schéma divergent, objet du travail en cours non commité). Risque de confusion au merge.
- **M11 — Autorisation incohérente** : `PUT /v2/sales/{id}/status` accepte n'importe quel utilisateur authentifié et un statut arbitraire non validé. (`v2_sales.py:815-826`)
- **M12 — Bug runtime `asyncio.run`** dans un endpoint async → `RuntimeError` à chaque ingestion de commande. (`v2_ingest.py:70`)
- **M13 — `POST /v2/sales/stages` inexistant** : la réorganisation du Kanban échoue silencieusement. (`SalesDashboard.jsx:196`)
- **M14 — `fetch('/api/v2/config/test-smtp')`** contourne la couche axios (pas de token) et le préfixe `/api` n'existe pas en prod nginx → test SMTP cassé. (`PlatformSettings.jsx:29`)

### Fonctionnel
- **M15 — Email client factice** : le code SMTP est entièrement commenté, fait un simple `print`. (`core/events.py:33-42`)
- **M16 — Signature de livraison perdue** : paramètre accepté puis ignoré. (`v2_logistics.py:64`)
- **M17 — Rôle `manager` seedé en ADMIN** : aucun compte ne teste réellement le rôle MANAGER ; 7 des 10 rôles RBAC sans aucun utilisateur.
- **M18 — Frontend v1, mobile Flutter, android_app : vestiges** — v1 appelle une route inexistante, Flutter synchronise vers un endpoint 404, android_app non buildable (fichiers Gradle manquants, `.bak` commités).

---

## 5. Problèmes mineurs (🟡)

- `requirements.txt` non épinglé (zéro version) → builds non reproductibles ; conteneur Docker en root, pas de `.dockerignore`.
- Montants en `Float` (erreurs d'arrondi comptables) ; `datetime.utcnow` naïf partout ; pas de contraintes CHECK.
- Routers monolithiques : `v2_stock.py` 1 602 lignes, `v2_sales.py` 1 302 lignes ; pages frontend de 1 500–2 900 lignes (`StockDashboard.jsx` 2 867 lignes).
- Double routing frontend : 9 vraies routes React Router + sous-routing `?view=` dans ManagerDashboard avec hack `SaleDetailRedirect`.
- Deux patterns de data-fetching incohérents (React Query vs useState/useEffect manuels) ; pas de TypeScript, tests ni linter frontend.
- axios 1.6.x (CVEs corrigées en ≥1.7.4) ; `react-signature-canvas` en alpha.
- Racine polluée : ~80 fichiers `*.md.resolved` / `*.metadata.json`, ~33 Mo de screenshots de debug `.webp/.png`, 9 `test_*.py` obsolètes hors collecte, scripts one-shot destructeurs (`alter_db.py`, `drop_tables.py`, `reset_odoo.py`), `package-lock.json` orphelin.
- Watcher OCR fantôme : l'upload promet un traitement OCR mais `watcher.py` n'est lancé nulle part ; `extractor.log` vide.
- N+1 sur le suivi des commandes et les factures en attente ; `print()` au lieu du logger ; `str(e)` renvoyé au client.
- SQLite par défaut fragile : chemin relatif au CWD, 4 fichiers `.db` cohabitent à la racine et dans `backend/`.

---

## 6. Cartographie fonctionnelle

| Module | État |
|---|---|
| Auth JWT + PIN + RBAC | ✅ Complet (backend) |
| Production / planning opérateur | ✅ Complet — parcours bouclé |
| Dashboards manager & analytics | ✅ Complet |
| Import débits atelier (Progers/Orgadata) | ✅ Complet, documenté, testé |
| Stock double-entrée + inventaires | ✅ Complet côté API |
| Ventes / devis / signature portail client | ✅ Complet — workflow bouclé (jamais alimenté en vraies données) |
| Facturation NF525 | ⚠️ Code complet, sceau non conforme, 2 factures de démo |
| Dossiers MMG (métrés, photos) | ❌ Cassé (routes front 404 + photos non servies) |
| Achats fournisseurs | ⚠️ Complet mais double API divergente |
| POS | ⚠️ Câblé, jamais utilisé (0 session) |
| Logistique / tournées | ⚠️ Partiel (signature non persistée) |
| Copilote IA devis | ⚠️ Dépend d'OPENAI_API_KEY, non documenté |
| WhatsApp / Email | ⚠️ Mock / coquille vide |
| Watcher OCR + surveillance | 🪦 Vestige supplanté par l'import débits |
| frontend v1, mobile Flutter, android_app | 🪦 Vestiges |

**Données actuelles (`atelier.db`)** : purement démo/test. Modules jamais exercés : clients (0), fournisseurs (0), dossiers MMG (0), POS (0), livraisons (0), paiements (0).

---

## 7. Plan d'action recommandé

### P0 — Sécurité immédiate
1. Ajouter `Depends(get_current_user)` au router `v2_pdf.py` (ou accès par token signé).
2. Supprimer la table PIN→username de `Login.jsx` ; changer les mots de passe seedés si la prod a été initialisée avec.
3. Recharger l'utilisateur en DB dans `get_current_user` + vérifier `is_active` ; réduire l'expiration JWT ≤ 12 h ; rate-limit sur `/token`.
4. Protéger ou supprimer `POST /orders/` ; authentifier le WebSocket.
5. Allowlist d'extensions + limite de taille sur tous les uploads.

### P1 — Correctifs fonctionnels
6. Corriger les 5 appels MMG du frontend (`/mmg/*` → `/v2/mmg/*`, PATCH pour le statut).
7. Monter `/static` ou migrer `v2_mmg` vers `/uploads` (une seule convention).
8. Remplacer les `COUNT+1` par des séquences transactionnelles ; refaire le sceau NF525 (HMAC + chaînage) ou retirer la mention de conformité.
9. Corriger `asyncio.run` (`v2_ingest.py:70`), implémenter `POST /v2/sales/stages`, réécrire `PlatformSettings.jsx` via l'instance axios.
10. Arbitrer le doublon fournisseurs avant de merger le travail en cours ; committer la migration `7c9d1e4a5b28`.

### P2 — Hygiène structurelle
11. Unifier la gestion de schéma (Alembic seul, stamping de la DB locale) ; sortir `create_all`/seeds de l'import (lifespan).
12. Épingler `requirements.txt` ; `USER` non-root + `.dockerignore` ; montants en `Numeric`, dates timezone-aware.
13. Purger les vestiges : `frontend/`, `mobile/`, `android_app/` (ou archiver), `watcher.py`/`surveillance.py`/`extractor.py`, scripts racine destructeurs, screenshots, `*.resolved*`, tests racine.
14. Réécrire la documentation vivante : un README décrivant le périmètre ERP actuel ; archiver `task.md`, `walkthrough.md`, les 15 `implementation_plan*.md`.
15. Créer un jeu de données de démo représentatif couvrant les 7 rôles et le cycle devis→prod→livraison→facture.
16. Ajouter des tests de contrat API (validation des chemins frontend contre `/openapi.json`) et des tests de sécurité (IDOR PDF, statuts arbitraires).

---

*Rapport généré par audit automatisé — chaque constat est adossé à un chemin de fichier et une ligne vérifiables.*

---

## Suivi des résolutions (2026-07-20)

| Chantier | Commit | Statut |
|---|---|---|
| P0 — IDOR PDF, JWT revérifié (12 h), `POST /orders/` + WebSocket authentifiés, PINs en dur supprimés, uploads validés | `6e6395d` | ✅ |
| P0 bis — 13 liens PDF back-office + 3 exports (FEC/CSV/XLSX) en téléchargement authentifié | `6e6395d` | ✅ |
| P1 — Routes MMG frontend (5×404) + photos servies via `/uploads/mmg/` | `f57228b` | ✅ |
| P1 — Doublon fournisseurs arbitré : unification sur `/v2/suppliers` (migration `7c9d1e4a5b28` validée) | `78e2a90` | ✅ |
| P1 — Numérotation transactionnelle (7 séquences) + sceau NF525 HMAC chaîné | `9e1a647` | ✅ |
| P2 — Purge : 182 fichiers (frontend v1, mobile Flutter, screenshots, artefacts, scripts destructeurs), watcher/surveillance/extractor → `scripts/legacy/`, docs historiques → `docs/archive/` | `46feca5` | ✅ |
| P2 — README vivant + jeu de données de démo idempotent (`scripts/seed_demo.py`) | `7034754` | ✅ |
| P2 — Unification schéma : Alembic seul, chaîne réparée (4 migrations batch), migration de rattrapage `e5c9f2a8d417`, lifespan sans effet de bord | `10f4c46` | ✅ |

**Tests : 70/70 verts.** Restes connus : `atelier.db` dev à resynchroniser via `scripts/reset_dev_db.sh` (non exécuté) ; `POST /v2/sales/stages` inexistant (Kanban non persistant) ; `fetch('/api/...')` de `PlatformSettings.jsx` cassé en prod ; `atelier_odoo_backup.db` à la racine non trackée (à confirmer pour suppression) ; montants en `Float` et dates naïves (P2 non traité).
