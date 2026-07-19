# Plan Dashboard V1

## Objectif
Visualiser les KPI de l'atelier simplement.

## Tech Stack
-   Frontend : HTML5 + CSS3 (Simple) + Vanilla JS.
-   Backend : Existant (FastAPI).

## Fonctionnalités
1.  **Vue Globale Jour** :
    -   Nombre d'ordres traités.
    -   Temps total atelier.

2.  **Vue par Poste** :
    -   Tableau : Poste | Moyenne Temps | % Ecart.
    -   Alerte visuelle (Rouge) si > 120% du temps standard (ex: 10min).

3.  **Détail Ordres** (Optionnel V1 mais utile) :
    -   Liste des ordres scannés ce jour.

## Architecture
-   `dashboard/index.html` : Structure.
-   `dashboard/style.css` : Design "Industriel" (Clair, Gros chiffres).
-   `dashboard/app.js` : Fetch API `/stats/daily` et manipulation DOM.

## Conformité V1
-   Pas de framework (React/Angular interdits implicitement par "Simplicité absolue").
-   Fichiers statiques servis par FastAPI (`StaticFiles`).

## Étapes
1.  Créer `backend/static/` (HTML/CSS/JS).
2.  Monter `StaticFiles` dans `main.py`.
3.  Implémenter `status_endpoint` enrichi pour donner les détails par poste.
