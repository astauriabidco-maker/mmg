# Plan Module Surveillance

## Objectif
Automatiser la création d'ordres à partir des fichiers PDF déposés par le logiciel PROGES.

## Étapes
1.  **Script `backend/surveillance.py`** :
    -   Utiliser `watchdog.observers.Observer`.
    -   Handler `FileSystemEventHandler.on_created`.
    -   Cible : Variable `WATCH_DIR` (Default: `C:\Exports_Proges\Validés\`).

2.  **Extraction PDF** :
    -   Fonction `extract_order_data(pdf_path)`.
    -   **Champs** :
        -   Ref : Regex `CMD-\d+` ou format spécifique.
        -   Dimensions : Recherche "Largeur: ...", "Hauteur: ...".
        -   Matière : Recherche "PVC" ou "ALU".

3.  **Génération QR** :
    -   Fonction `generate_qr(ref, width, height, material)`.
    -   Contenu : `f"{ref}|{width}x{height}|{material}"`.
    -   Format : PNG, 50x30mm (approx 190x115 px ? à définir en DPI).
    -   Sauvegarde dans un dossier `output/qr/`.

4.  **Intégration** :
    -   Appel `create_order` (importé de main/crud) pour insérer en base.

## Conformité V1
-   Pas de service complexe, juste un script lancé en parallèle ou via un process manager simple (non inclus, le script suffit).
-   Bibliothèques standards + légères (`pypdf`, `watchdog`).
-   Postes fixes non concernés ici (c'est la création d'ordre).

## Test
-   Déposer un PDF factice.
-   Vérifier la création de l'ordre en base.
-   Vérifier la création du fichier QR.
