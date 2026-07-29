# Recette CRM → débit avec backend réel

Cette recette démarre deux services locaux :

- FastAPI sur `127.0.0.1:7100`, avec une base SQLite et un répertoire d'uploads
  temporaires ;
- Vite sur `127.0.0.1:5173`, configuré pour utiliser ce backend.

Elle utilise un utilisateur administrateur et un dossier signé créés dans la base
jetable. Les fichiers de fabrication et de débit sont générés en mémoire avec des
références anonymisées. Aucun PDF client n'est lu ou copié.

Exécution :

```bash
cd frontend_v2
npm run test:e2e:real
```

Le scénario couvre dans le navigateur l'import des deux documents, la validation
BE, la validation stock, la création de la réservation, l'autorisation atelier
et le lancement de la production. Il poursuit ensuite sur le même backend réel
avec les appels de préparation, remise atelier et consommation, puis vérifie les
états finaux `consumed` et `IN_PRODUCTION`.

Limite actuelle : les gestes magasin de préparation, remise et consommation sont
pilotés par le client HTTP Playwright plutôt que par les écrans du module Stock.
Le backend, les permissions, la base et les mutations sont néanmoins réels. Une
recette dédiée au terminal magasin pourra compléter la validation purement UI.
