# Plan Module QR Generator (Zebra ZD420)

## Objectif
Générer et imprimer des étiquettes 50x30mm contenant un QR Code et du texte lisible.

## Spécifications
-   **Format** : PDF 50mm x 30mm.
-   **Contenu QR** : `CMD-XXXX|LxH|MATIERE`.
-   **Texte** :
    -   Ligne 1 : CMD-XXXX
    -   Ligne 2 : LxH mm
-   **Hardware** : Zebra ZD420 (Support PDF direct ou via driver).

## Architecture
### `backend/qr_generator.py`
-   Dépendance : `reportlab` (Précision millimétrique).
-   Fonction `generate_label(data: dict) -> str`: Retourne le chemin du PDF généré.
-   Fonction `_create_qr_image(content)` : Utilise `qrcode`.

### `backend/printer.py`
-   Fonction `print_label(file_path: str)` :
    -   Tentative impression système (`lp` ou `lpr` sur Mac/Linux, `powershell` sur Windows).
    -   Gestion erreur : Appel `backend.alerting.send_alert`.

### `backend/alerting.py` (Nouveau)
-   Fonction `send_email_alert(subject, body)` : SMTP simple (Gmail/Outlook/Local).
-   Configuration via Env Vars.

## Tests
-   `test_qr_generator.py` : Vérifie la création du fichier et ses dimensions (via Metadata PDF).

## Conformité V1
-   Pas de design complexe (Noir/Blanc, Font standard).
-   Pas de multi-format (Hardcoded 50x30mm).
-   Validé lisible (QR version 1 ou 2, ECC L ou M).
