# Import stock réel

Le script `scripts/import_real_stock.py` traite le fichier Excel multi-fournisseurs utilisé pour le stock réel MMG.

Format reconnu :

- ligne 1 : fournisseur ;
- ligne 3 : bloc répété `Réf`, `Nom de l'accessoire`, `Quant`, `Gamme`, `iIlustration` ;
- lignes suivantes : articles.

Le script consolide prudemment les doublons par couple `fournisseur + référence` :

- même référence + même désignation : une seule fiche est conservée, les gammes sont fusionnées, la quantité n'est pas cumulée ;
- même référence + quantité différente : alerte de contrôle, la quantité est conservée une seule fois ;
- même référence + désignation différente : conflit bloquant, la référence est ignorée jusqu'à arbitrage manuel ;
- référence vide, `/`, `x`, etc. : ligne ignorée.

## Prévisualiser sans écrire

```bash
python3 scripts/import_real_stock.py "/chemin/tableau à envoyer.xlsx" \
  --compare-db \
  --json-out ./stock-preview.json \
  --issues-csv ./stock-issues.csv
```

La prévisualisation remonte :

- doublons fournisseur/référence ;
- lignes sans référence ;
- quantités vides ou invalides (signalées et exclues de l'import) ;
- désignations vides ;
- nombre d'articles importables.
- comparaison optionnelle avec la base active (`--compare-db`) : références déjà présentes, nouvelles références, échantillon des correspondances.
- rapport CSV optionnel (`--issues-csv`) : liste exploitable des conflits, lignes sans référence, désignations manquantes et quantités à vérifier.

## Importer en base

Faire un backup PostgreSQL avant l'import.

```bash
python3 scripts/import_real_stock.py "/chemin/tableau à envoyer.xlsx" \
  --apply \
  --location "WH/Stock"
```

Si la prévisualisation contient des erreurs bloquantes, `--apply` refuse d'écrire.
Corriger le fichier ou relancer explicitement avec `--allow-errors` pour ignorer les lignes bloquantes déjà exclues de l'import.
Les lignes dont la quantité est vide, `/`, `?` ou non numérique restent dans le rapport d'anomalies mais ne sont jamais converties automatiquement en stock zéro.

L'import crée ou met à jour :

- `products` avec `reference_base = fournisseur:référence` ;
- `product_variants` avec `reference = fournisseur:référence` et `supplier_reference = référence` ;
- `stock_quants` sur l'emplacement choisi ;
- `stock_moves` d'initialisation quand la quantité change.

Les quantités passent par `InventoryService` et créent des mouvements entre `Virtual/Inventory` et l'emplacement cible. Le script ne modifie pas directement le stock sans trace.

Valeurs par défaut :

- `unit = pce`
- `material_type = ACCESSOIRE`
- `product_type = stockable`

## Remarques pour les futurs fichiers de débit

Les fichiers Proges/Orgadata devront être rapprochés via :

- `product_variants.reference` si le fichier contient une clé MMG `fournisseur:référence` ;
- `product_variants.supplier_reference` si le fichier ne contient que la référence fournisseur.

Si une même référence fournisseur existe chez plusieurs fournisseurs, il faudra ajouter une règle de mapping explicite avant décrémentation automatique du stock.
