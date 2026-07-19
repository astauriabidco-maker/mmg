import base64
import binascii
import os
import uuid
from typing import Optional, Set, Tuple

from fastapi import HTTPException, UploadFile

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 Mo
# Le base64 amplifie ~4/3 : on borne le payload encodé AVANT décodage
# pour éviter l'amplification mémoire.
MAX_BASE64_PAYLOAD_LENGTH = ((MAX_UPLOAD_BYTES + 2) // 3) * 4 + 1024

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}

ALLOWED_CONTENT_TYPES = {
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".webp": {"image/webp"},
    ".pdf": {"application/pdf"},
    ".txt": {"text/plain"},
}

_MIME_TO_EXTENSION = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def validate_extension(filename: Optional[str], extra_extensions: Optional[Set[str]] = None) -> str:
    allowed = set(ALLOWED_EXTENSIONS)
    if extra_extensions:
        allowed.update(ext.lower() for ext in extra_extensions)
    extension = os.path.splitext(filename or "")[1].lower()
    if extension not in allowed:
        raise HTTPException(status_code=400, detail="Extension de fichier non autorisée.")
    return extension


def validate_content_type(content_type: Optional[str], extension: str) -> None:
    # Contrôlé seulement quand le client fournit un content-type exploitable.
    if not content_type or content_type == "application/octet-stream":
        return
    expected = ALLOWED_CONTENT_TYPES.get(extension)
    if expected and content_type.lower() not in expected:
        raise HTTPException(status_code=400, detail="Type de contenu non autorisé.")


def generate_safe_filename(extension: str, prefix: str = "") -> str:
    # Le nom client n'est jamais réutilisé : uuid + extension allowlistée.
    return f"{prefix}{uuid.uuid4().hex}{extension}"


async def save_upload_file(
    file: UploadFile,
    directory: str,
    extra_extensions: Optional[Set[str]] = None,
    prefix: str = "",
) -> str:
    """Valide (extension, content-type, taille) puis sauvegarde sous un nom uuid."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nom de fichier manquant.")
    extension = validate_extension(file.filename, extra_extensions)
    validate_content_type(file.content_type, extension)

    os.makedirs(directory, exist_ok=True)
    safe_filename = generate_safe_filename(extension, prefix)
    file_path = os.path.join(directory, safe_filename)

    total = 0
    exceeded = False
    with open(file_path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                exceeded = True
                break
            buffer.write(chunk)
    if exceeded:
        os.remove(file_path)
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 10 Mo).")
    return file_path


def decode_base64_upload(data: str) -> Tuple[bytes, str]:
    """Décode un payload base64 (data URL acceptée) avec bornes de taille.

    Retourne (contenu, extension allowlistée déduite du MIME déclaré, .png sinon).
    """
    if not data:
        raise HTTPException(status_code=400, detail="Données base64 manquantes.")

    declared_mime = None
    payload = data
    if "base64," in data:
        header, payload = data.split("base64,", 1)
        if header.startswith("data:"):
            declared_mime = header[5:].rstrip(";").lower() or None

    if len(payload) > MAX_BASE64_PAYLOAD_LENGTH:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 10 Mo).")

    try:
        content = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Payload base64 invalide.")

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 10 Mo).")

    extension = ".png"
    if declared_mime:
        if declared_mime not in _MIME_TO_EXTENSION:
            raise HTTPException(status_code=400, detail="Type de contenu non autorisé.")
        extension = _MIME_TO_EXTENSION[declared_mime]
    return content, extension
