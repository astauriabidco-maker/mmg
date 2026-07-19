# Plan Interface Web Jinja2 (V1)

## Objectif
Interface opérateur/surviseur intégrée au backend (Pas de React).

## Stack
-   Backend: FastAPI
-   Templating: Jinja2
-   DB: SQLite
-   CSS: Natif simple

## Structure
1.  **Templates**
    -   `backend/templates/index.html`: Page unique contenant :
        -   Tableau de bord (KPIs simples + Liste Logs).
        -   Formulaire START (POST /web/start).
        -   Formulaire STOP (POST /web/stop).
2.  **Backend (`main.py`)**
    -   Ajout routes HTML.
    -   Logique de calcul "en direct" pour le template (Alertes CSS).

## Règles Métier (Rappel)
-   Postes Autorisés : Liste fixée (10 postes).
-   Standards : PVC=300s, ALU=600s.
-   Alerte : Durée > 120% -> Ligne rouge.

## Tâches
- [ ] Requirements (`jinja2`, `python-multipart`).
- [ ] Création dossier `backend/templates`.
- [ ] Création `backend/templates/index.html`.
- [ ] Modification `backend/main.py` pour inclure la logique Web.
