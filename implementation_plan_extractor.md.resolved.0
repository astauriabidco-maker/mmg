# Plan Module Extractor Indépendant

## Objectif
Créer un module robuste pour extraire CMD, Largeur, Hauteur, Matière des PDF PROGES, avec fallback OCR.

## Architecture
### 1. `backend/extractor.py`
Classe `PDFExtractor`.
-   **Entrée** : Chemin fichier.
-   **Sortie** : Dict JSON `{ "reference": "...", "width": 0.0, "height": 0.0, "material": "..." }`.
-   **Logique** :
    1.  Tentative extraction native (`pypdf`).
    2.  Validation (Si texte vide ou manque champs).
    3.  Si échec : Tentative OCR (`pdf2image` + `pytesseract`).
    4.  Parsing Regex sur le texte complet.

### 2. `backend/watcher.py`
Script indépendant.
-   Surveille `C:\Exports_Proges\Validés\`.
-   Utilise `PDFExtractor`.
-   Loggue les résultats.
-   (Optionnel v1) Envoie au backend ou stocke JSON localement. Le prompt demande "Retour JSON formaté prêt à être envoyé".

## Dépendances
-   `pypdf` (Existant)
-   `pytesseract` (Nouveau - OCR)
-   `pdf2image` (Nouveau - Conversion PDF->Img pour OCR)
-   *Note : Nécessite Tesseract et Poppler installés sur la machine hôte.*

## Tests
-   Mocker `pypdf` et `pytesseract` pour valider la logique de bascule et les regex.

## Conformité
-   Respecte "OCR fallback si nécessaire".
-   Logging obligatoire.
-   Gestion erreur propre.
