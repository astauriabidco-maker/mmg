# Plan Dashboard React V1

## Objectif
Dashboard de surveillance atelier temps réel (Refresh 15s).

## Backend (API)
### Endpoint: `GET /dashboard/metrics`
**Response JSON**:
```json
{
  "kpi": {
    "active_orders": 12,
    "global_avg_seconds": 450,
    "alerts_percent": 5.5
  },
  "pvc": [
    { "station": "PVC_DEBIT", "avg_seconds": 310 }
  ],
  "alu": [
    { "station": "ALU_DEBIT", "avg_seconds": 620 }
  ],
  "alerts": [
    { "order": "CMD-101", "station": "PVC_SOUDURE", "duration": 400, "limit": 300 }
  ]
}
```

### Logique Business
-   **Standards** (Hardcodés V1):
    -   PVC: 300s (5min)
    -   ALU: 600s (10min)
    -   Seuil Alerte: 120% (360s / 720s).

## Frontend (React)
-   **Stack**: Vite, React, Axios.
-   **Structure**:
    -   `App.jsx`: Layout Grid.
    -   `components/KPI.jsx`.
    -   `components/StationTable.jsx`.
    -   `components/AlertBox.jsx`.
-   **Style**: CSS Grid simple ou Tailwind (je vais utiliser CSS pur pour "Simple" sauf si Tailwind est demandé explicitement, le prompt dit "React Simple", je vais éviter la lourdeur de Tailwind setup si non nécessaire, mais Vite+React+CSS Modules est très propre).

## Conformité
-   Chargement < 2s (Bundle minifié Vite).
-   Pas de graphiques (Tableaux et Cards).
-   Rafraîchissement 15s.
