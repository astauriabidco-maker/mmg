# Plan d'Implémentation Backend V1

## Objectif
Mettre en place le cœur du système : une API REST simple et robuste pour gérer les ordres de fabrication et les temps de passage.

## Validation de Conformité
- **Stack** : Python 3.11, FastAPI, SQLite.
- **Architecture** : Monolithe.
- **Interdictions** : Pas de Docker, pas de Redis, auth simple (si besoin later).

## Modifications Proposées

### [NEW] requirements.txt
- fastapi
- uvicorn
- sqlalchemy
- pydantic

### [NEW] backend/database.py
- Configuration SQLite (fichier local `atelier.db`).
- SessionLocal et Base pour SQLAlchemy.

### [NEW] backend/models.py
- **Order** : ref (CMD-XXXX), width, height, material (PVC/ALU).
- **Station** : name (Enum strict Section 3), type (PVC/ALU).
- **TimeLog** : order_id, station_id, start_time, end_time, duration.

### [NEW] backend/main.py
- Initialisation FastAPI.
- Création automatique des tables au démarrage.
- Endpoint de santé `/health`.

## Plan de Vérification
### Tests Automatisés
- Script `test_backend.py` :
    1. Créer une commande test.
    2. Simuler un scan (Start).
    3. Simuler un scan (Stop).
    4. Vérifier le calcul de durée dans SQLite.

### Vérification Manuelle
- Lancer `uvicorn backend.main:app --reload`.
- Accéder à `/docs` (Swagger UI).
- Tester les endpoints manuellement.
