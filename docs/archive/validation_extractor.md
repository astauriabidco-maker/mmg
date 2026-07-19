# Rapport Validation - Module Extractor Indépendant

## 1. Fonctionnalités
- [x] Détection PDF (Watcher)
- [x] Extraction Native (pypdf)
- [x] Extraction OCR Fallback (pytesseract/pdf2image)
- [x] Parsing Regex (CMD, Largeur, Hauteur, Matière)
- [x] Sortie JSON

## 2. Qualité
- [x] Logging structuré (`extractor.log`)
- [x] Gestion d'erreurs (Try/Catch global)
- [x] Tests Unitaires (30 cas simulés, couverture cas limites)

## 3. Conformité V1
- Pas de modification du PDF original.
- Pas de logique métier complexe (juste extraction).
- Indépendant du backend (Script standalone).

## 4. Usage
```bash
python3 backend/watcher.py
```
Le watcher surveille `C:\Exports_Proges\Validés` (ou dossier configuré) et loggue le JSON résultat.
