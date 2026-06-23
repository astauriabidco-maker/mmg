# Import stock réel

Le script `scripts/import_real_stock.py` traite le fichier Excel multi-fournisseurs utilisé pour le stock réel MMG.

Format reconnu :

- ligne 1 : fournisseur ;
- ligne 3 : bloc répété `Réf`, `Nom de l'accessoire`, `Quant`, `Gamme`, `iIlustration` ;
- lignes suivantes : articles.

Le script consolide les doublons par couple `fournisseur + référence`.

## Prévisualiser sans écrire

```bash
python3 scripts/import_real_stock.py "/chemin/tableau à envoyer.xlsx" \
  --json-out ./stock-preview.json
```

La prévisualisation remonte :

- doublons fournisseur/référence ;
- lignes sans référence ;
- quantités vides ou invalides ;
- désignations vides ;
- nombre d'articles importables.

## Importer en base

Faire un backup PostgreSQL avant l'import.

```bash
python3 scripts/import_real_stock.py "/chemin/tableau à envoyer.xlsx" \
  --apply \
  --location "WH/Stock"
```

Si la prévisualisation contient des erreurs bloquantes, `--apply` refuse d'écrire.
Corriger le fichier ou relancer explicitement avec `--allow-errors` pour ignorer les lignes bloquantes déjà exclues de l'import.

L'import crée ou met à jour :

- `products` avec `reference_base = fournisseur:référence` ;
- `product_variants` avec `reference = fournisseur:référence` et `supplier_reference = référence` ;
- `stock_quants` sur l'emplacement choisi ;
- `stock_moves` d'initialisation quand la quantité change.

Valeurs par défaut :

- `unit = pce`
- `material_type = ACCESSOIRE`
- `product_type = stockable`

## Remarques pour les futurs fichiers de débit

Les fichiers Proges/Orgadata devront être rapprochés via :

- `product_variants.reference` si le fichier contient une clé MMG `fournisseur:référence` ;
- `product_variants.supplier_reference` si le fichier ne contient que la référence fournisseur.

Si une même référence fournisseur existe chez plusieurs fournisseurs, il faudra ajouter une règle de mapping explicite avant décrémentation automatique du stock.
