# Instructions de Build - Dashboard React

## 1. Installation
```bash
cd frontend
npm install
```

## 2. Développement (Hot Reload)
```bash
npm run dev
```
*Note : Pour que l'API fonctionne en local, configurez un proxy dans vite.config.js ou activez CORS sur FastAPI.*

## 3. Build Production (Intégration FastAPI)
```bash
npm run build
```
Le build génère les fichiers statiques (html, css, js) directement dans `../backend/static`.

## 4. Accès
Une fois le backend lancé (`uvicorn backend.main:app ...`) :
[http://localhost:8000/dashboard_ui/index.html](http://localhost:8000/dashboard_ui/index.html)
