# Plan Implémentation V2 - Atelier Connecté

## Objectifs du Sprint 2
Passer d'un outil de suivi passif (V1) à un système de pilotage temps réel et interactif.

## Architecture Cible
-   **Backend** : FastAPI (inchangé) + **WebSockets**.
-   **Frontend** : **React (Vite)** (Remplacement de Jinja2 pour l'interactivité).
-   **Base de Données** : SQLite (Ajout tables Users, Planning).

## Fonctionnalités & Modules

### 1. Authentification & Opérateurs
-   **Besoin** : Savoir *qui* travaille.
-   **Solution** : Login par **Code PIN** (4 chiffres) ou Badge (Simulation clavier).
-   **Tech** : Table `users`, Endpoint `/auth/login` (JWT).

### 2. Planning & Ordonnancement
-   **Besoin** : Fin de la saisie papier. L'opérateur voit ce qu'il doit faire.
-   **Solution** : Vue "File d'attente" par poste.
-   **Tech** : Table `planning` (order_id, station, priority, status).
-   **UI** : Drag & Drop pour le Manager (optionnel) ou liste priorisée.

### 3. Temps Réel (WebSockets)
-   **Besoin** : Mise à jour écran sans F5.
-   **Solution** : WebSocket `/ws/production`.
-   **Events** : `log_update`, `alert_new`, `planning_change`.

### 4. Interface Tactile (Opérateur)
-   **Besoin** : Usage doigt/gant, écran 10".
-   **Design** :
    -   Boutons START/STOP géants.
    -   Code couleur fort (Vert/Rouge).
    -   Liste des tâches "À Faire" à gauche.

### 5. Analytics (Manager)
-   **Besoin** : Comprendre les performances.
-   **Solution** : Graphiques (Recharts).
    -   Pareto des arrêts / défauts.
    -   OEE (TRG) par poste.
    -   Evolution temps moyen/semaine.

## Plan de Migration
1.  **Backend Upgrade** :
    -   Ajout modèles `User`, `Planning`.
    -   Setup Auth (JWT).
    -   Setup WebSockets.
2.  **Frontend Setup** :
    -   Init React (Vite).
    -   Setup API Client (Axios) + WebSocket Client.
3.  **Dév Modules** :
    -   Auth (Login Screen).
    -   Operator View (Planning + Actions).
    -   Manager View (Analytics).
4.  **Déploiement** :
    -   Build React servi par FastAPI (`StaticFiles`).

## Risques
-   Complexité React vs Jinja (Courbe d'apprentissage maintenance).
-   Gestion WebSockets (Connexions perdues). -> Prévoir Reconnection auto.
