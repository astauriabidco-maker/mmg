# Import des débits atelier

Ce flux sert à prévisualiser puis réserver des consommations de stock issues de logiciels tiers.

Formats pris en charge au premier passage :

- Progers/Proges `.TXT` avec lignes séparées par `;`.
- Orgadata/Logikal `Débit optimisé.pdf` pour les besoins en barres.

Les PDF de type bon atelier ou valorisation sont lus mais non débités automatiquement pour l'instant. Ils restent utiles comme pièces de contrôle.

## Prévisualiser

```bash
python scripts/import_workshop_debits.py \
  SEPVER.TXT \
  Optimisation.pdf \
  --json-out /tmp/workshop-debit-preview.json
```

La prévisualisation indique :

- les lignes de débit détectées ;
- les fournisseurs et unités ;
- les références inconnues ;
- les quantités demandées, disponibles et manquantes.

## Règle métier

L'import d'un fichier atelier ne débite pas définitivement le stock. Il crée une réservation virtuelle.

Le stock est débité définitivement quand l'étape réelle `Débit PVC` ou `Débit ALU` est terminée en atelier. La réservation est alors consommée et MMG crée les mouvements `WH/Stock -> Production Ateliers`.

## Réserver depuis l'application

Dans `Inventaire & Stock`, utiliser `Débit Atelier` :

1. Sélectionner un devis validé (`VALIDATED`, `READY_FOR_PROD` ou `IN_PRODUCTION`).
2. Ajouter le TXT Progers et/ou le PDF `Débit optimisé` Orgadata.
3. Lancer la prévisualisation.
4. Corriger les références inconnues, le stock insuffisant ou une incohérence matière.
5. Réserver le stock.

Contrôles obligatoires :

- une réservation doit être liée à un devis validé ou à un ordre de production ;
- un devis brouillon/envoyé non signé est refusé ;
- une réservation active existe au maximum une fois par devis ;
- la matière détectée dans les fichiers (`ALU`, `PVC`) doit être cohérente avec le devis/ordre quand MMG peut l'inférer ;
- les forçages `--allow-missing` et `--allow-shortage` sont réservés aux administrateurs.

## Appliquer en base via CLI

Le script CLI garde une option `--apply` pour les opérations techniques contrôlées, mais le flux produit recommandé passe par la réservation applicative.

```bash
python scripts/import_workshop_debits.py \
  SEPVER.TXT \
  Optimisation.pdf \
  --apply \
  --json-out /tmp/workshop-debit-result.json
```

Les mouvements créés par le CLI transfèrent directement le stock de `WH/Stock` vers `Production Ateliers`.

Options de secours :

```bash
--allow-missing
--allow-shortage
```

Ces options doivent rester exceptionnelles, après validation métier.

## Coolify

Copier les fichiers dans le backend actif :

```bash
sudo docker cp /home/bo3oo/SEPVER.TXT NOM_BACKEND:/tmp/SEPVER.TXT
sudo docker cp /home/bo3oo/Optimisation.pdf NOM_BACKEND:/tmp/Optimisation.pdf
```

Prévisualiser :

```bash
sudo docker exec -it NOM_BACKEND \
  python scripts/import_workshop_debits.py \
  /tmp/SEPVER.TXT \
  /tmp/Optimisation.pdf \
  --json-out /tmp/workshop-debit-preview.json
```

Pour le flux produit, réserver depuis l'application puis laisser l'étape atelier consommer la réservation. L'application expose aussi les API :

```bash
POST /v2/stock/workshop-debits/preview
POST /v2/stock/workshop-debits/reservations
POST /v2/stock/workshop-debits/reservations/{id}/consume
```

Débit direct CLI seulement après validation technique :

```bash
sudo docker exec -it NOM_BACKEND \
  python scripts/import_workshop_debits.py \
  /tmp/SEPVER.TXT \
  /tmp/Optimisation.pdf \
  --apply \
  --json-out /tmp/workshop-debit-result.json
```
