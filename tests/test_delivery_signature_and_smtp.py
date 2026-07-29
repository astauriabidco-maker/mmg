"""Persistance de la signature de livraison + envoi SMTP réel (mocké).

Couvre :
- POST /v2/logistics/notes/{id}/deliver : la signature base64 est décodée via
  backend/core/uploads.py, écrite sous uploads/delivery/ et le chemin est
  persisté (colonne signature_path) puis exposé dans la réponse.
- EventBus.send_quote_for_signature_email : le devis et son lien de signature
  sont réellement envoyés, avec un résultat SENT/SKIPPED/FAILED exploitable.
- EventBus._task_send_quote_confirmation_email : envoi SMTP réel via smtplib
  (mocké) quand la config d'environnement est complète, skip gracieux sinon,
  et jamais d'exception propagée si le transport SMTP échoue (l'email est
  best-effort, le flux métier de signature prime).
- Le flux portail /v2/sales/portal/{token}/sign déclenche bien l'email de
  confirmation au client.
"""

import base64
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend import models  # noqa: E402
from backend.core.events import EventBus  # noqa: E402
from backend.core.security import get_password_hash  # noqa: E402

# PNG 1x1 minimal valide
_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
_PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(_PNG_BYTES).decode()

_SMTP_ENV = {
    "SMTP_HOST": "smtp.example.test",
    "SMTP_PORT": "587",
    "SMTP_USER": "contact@mmg.test",
    "SMTP_PASSWORD": "secret",
    "SMTP_FROM": "contact@mmg.test",
    "SMTP_USE_TLS": "true",
}


def _clear_smtp_env(monkeypatch):
    for key in _SMTP_ENV:
        monkeypatch.delenv(key, raising=False)


def _set_smtp_env(monkeypatch):
    for key, value in _SMTP_ENV.items():
        monkeypatch.setenv(key, value)


def _create_admin(TestingSessionLocal):
    with TestingSessionLocal() as db:
        db.add(
            models.User(
                username="admin",
                pin_hash=get_password_hash("1234"),
                role="ADMIN",
                is_active=True,
            )
        )
        db.commit()


def _admin_headers(client: TestClient) -> dict:
    response = client.post("/token", data={"username": "admin", "password": "1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_delivery_note(TestingSessionLocal, reference="BL-2026-0001") -> int:
    with TestingSessionLocal() as db:
        note = models.DeliveryNote(
            reference=reference,
            client_name="Client Livraison",
            delivery_address="10 rue du Port, 44000 Nantes",
            status="READY",
        )
        db.add(note)
        db.commit()
        db.refresh(note)
        return note.id


# --- SIGNATURE DE LIVRAISON ---

def test_deliver_persists_signature_image(isolated_client, monkeypatch, tmp_path):
    client, TestingSessionLocal = isolated_client
    _create_admin(TestingSessionLocal)
    headers = _admin_headers(client)
    note_id = _create_delivery_note(TestingSessionLocal)
    # Les uploads sont écrits en relatif : on isole dans tmp_path.
    monkeypatch.chdir(tmp_path)

    response = client.post(
        f"/v2/logistics/notes/{note_id}/deliver",
        json={"signature_image": _PNG_DATA_URL},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "DELIVERED"
    assert body["signed_at"] is not None
    signature_path = body["signature_path"]
    assert signature_path.startswith("uploads/delivery/")
    assert signature_path.endswith(".png")

    # Le fichier existe sur disque et contient bien l'image décodée.
    saved = tmp_path / signature_path
    assert saved.is_file()
    assert saved.read_bytes() == _PNG_BYTES

    # Le chemin est persisté en base.
    with TestingSessionLocal() as db:
        note = db.query(models.DeliveryNote).filter(models.DeliveryNote.id == note_id).first()
        assert note.signature_path == signature_path

    # Le BL PDF se génère avec la signature incrustée (image valide).
    pdf_response = client.get(f"/v2/pdf/delivery-note/{note_id}", headers=headers)
    assert pdf_response.status_code == 200, pdf_response.text
    assert pdf_response.headers["content-type"] == "application/pdf"


def test_deliver_without_signature_still_works(isolated_client):
    client, TestingSessionLocal = isolated_client
    _create_admin(TestingSessionLocal)
    headers = _admin_headers(client)
    note_id = _create_delivery_note(TestingSessionLocal, reference="BL-2026-0002")

    response = client.post(
        f"/v2/logistics/notes/{note_id}/deliver",
        json={},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "DELIVERED"
    assert body["signature_path"] is None


def test_deliver_rejects_invalid_signature_payload(isolated_client):
    client, TestingSessionLocal = isolated_client
    _create_admin(TestingSessionLocal)
    headers = _admin_headers(client)
    note_id = _create_delivery_note(TestingSessionLocal, reference="BL-2026-0003")

    response = client.post(
        f"/v2/logistics/notes/{note_id}/deliver",
        json={"signature_image": "!!!pas-du-base64!!!"},
        headers=headers,
    )
    assert response.status_code == 400, response.text


# --- SMTP : ENVOI RÉEL, SKIP GRACIEUX, BEST-EFFORT ---

def test_smtp_email_sent_with_expected_content_when_configured(monkeypatch):
    _set_smtp_env(monkeypatch)
    with patch("backend.core.events.smtplib.SMTP") as smtp_cls:
        server = smtp_cls.return_value.__enter__.return_value
        EventBus._task_send_quote_confirmation_email(
            "alice@example.test", "ACME Renovation", "DEV-2026-0042", 4320.0,
            "https://mmg.test/portal/sign/token-abc",
        )

    smtp_cls.assert_called_once_with("smtp.example.test", 587, timeout=15)
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("contact@mmg.test", "secret")
    server.send_message.assert_called_once()
    msg = server.send_message.call_args[0][0]
    assert msg["To"] == "alice@example.test"
    assert msg["From"] == "contact@mmg.test"
    assert "DEV-2026-0042" in msg["Subject"]
    plain_part = msg.get_payload()[0].get_payload(decode=True).decode("utf-8")
    assert "DEV-2026-0042" in plain_part
    assert "4 320,00 € TTC" in plain_part
    assert "https://mmg.test/portal/sign/token-abc" in plain_part
    html_part = msg.get_payload()[1].get_payload(decode=True).decode("utf-8")
    assert "DEV-2026-0042" in html_part


def test_smtp_quote_for_signature_sent_with_expected_content(monkeypatch):
    _set_smtp_env(monkeypatch)
    with patch("backend.core.events.smtplib.SMTP") as smtp_cls:
        server = smtp_cls.return_value.__enter__.return_value
        result = EventBus.send_quote_for_signature_email(
            "alice@example.test",
            "ACME Renovation",
            "DEV-2026-0042",
            4320.0,
            "https://mmg.test/portal/sign/token-abc",
        )

    assert result == {
        "status": "SENT",
        "recipient": "alice@example.test",
        "error": None,
    }
    server.send_message.assert_called_once()
    msg = server.send_message.call_args[0][0]
    assert msg["To"] == "alice@example.test"
    assert msg["Subject"] == "Votre devis DEV-2026-0042 à signer - MMG"
    plain_part = msg.get_payload()[0].get_payload(decode=True).decode("utf-8")
    assert "4 320,00 € TTC" in plain_part
    assert "https://mmg.test/portal/sign/token-abc" in plain_part


def test_sent_status_sends_and_can_resend_quote_email(isolated_client, monkeypatch):
    client, TestingSessionLocal = isolated_client
    _create_admin(TestingSessionLocal)
    headers = _admin_headers(client)
    _set_smtp_env(monkeypatch)

    create_response = client.post(
        "/v2/sales/",
        json={
            "client_name": "ACME Renovation",
            "client_email": "alice@example.test",
            "validity_days": 30,
            "tax_rate": 20.0,
            "currency": "EUR",
            "lines": [
                {
                    "variant_id": None,
                    "description": "Fenêtre de recette",
                    "quantity": 1,
                    "unit_price": 1000.0,
                    "discount_pct": 0,
                    "visual_config": None,
                },
            ],
        },
        headers=headers,
    )
    assert create_response.status_code == 200, create_response.text
    sale = create_response.json()

    with patch("backend.core.events.smtplib.SMTP") as smtp_cls:
        server = smtp_cls.return_value.__enter__.return_value
        sent_response = client.put(
            f"/v2/sales/{sale['id']}/status",
            params={"status": "SENT"},
            headers=headers,
        )
        resend_response = client.put(
            f"/v2/sales/{sale['id']}/status",
            params={"status": "SENT"},
            headers=headers,
        )

    assert sent_response.status_code == 200, sent_response.text
    assert sent_response.json()["email_status"] == "SENT"
    assert sent_response.json()["email_recipient"] == "alice@example.test"
    assert resend_response.status_code == 200, resend_response.text
    assert resend_response.json()["email_status"] == "SENT"
    assert server.send_message.call_count == 2

    with TestingSessionLocal() as db:
        logs = (
            db.query(models.ChatterMessage)
            .filter(
                models.ChatterMessage.model_name == "sale_order",
                models.ChatterMessage.record_id == sale["id"],
            )
            .all()
        )
    assert len(logs) == 2
    assert all("envoyé pour signature" in item.body for item in logs)


def test_smtp_email_skipped_gracefully_when_not_configured(monkeypatch):
    _clear_smtp_env(monkeypatch)
    with patch("backend.core.events.smtplib.SMTP") as smtp_cls:
        # Aucune exception, aucun appel SMTP.
        EventBus._task_send_quote_confirmation_email(
            "alice@example.test", "ACME Renovation", "DEV-2026-0042", 4320.0,
        )
    smtp_cls.assert_not_called()


def test_smtp_email_skipped_when_no_recipient(monkeypatch):
    _set_smtp_env(monkeypatch)
    with patch("backend.core.events.smtplib.SMTP") as smtp_cls:
        EventBus._task_send_quote_confirmation_email(
            None, "ACME Renovation", "DEV-2026-0042", 4320.0,
        )
    smtp_cls.assert_not_called()


def test_smtp_failure_never_raises(monkeypatch):
    _set_smtp_env(monkeypatch)
    with patch("backend.core.events.smtplib.SMTP") as smtp_cls:
        smtp_cls.return_value.__enter__.return_value.send_message.side_effect = OSError("connexion refusée")
        # Ne doit JAMAIS lever : l'email est best-effort.
        EventBus._task_send_quote_confirmation_email(
            "alice@example.test", "ACME Renovation", "DEV-2026-0042", 4320.0,
        )


def test_smtp_connection_failure_never_raises(monkeypatch):
    _set_smtp_env(monkeypatch)
    with patch("backend.core.events.smtplib.SMTP", side_effect=OSError("hôte injoignable")):
        EventBus._task_send_quote_confirmation_email(
            "alice@example.test", "ACME Renovation", "DEV-2026-0042", 4320.0,
        )


# --- DÉCLENCHEMENT À LA SIGNATURE PORTAIL ---

def test_portal_sign_triggers_confirmation_email(isolated_client, monkeypatch):
    client, TestingSessionLocal = isolated_client
    _create_admin(TestingSessionLocal)
    headers = _admin_headers(client)
    _set_smtp_env(monkeypatch)

    create_response = client.post(
        "/v2/sales/",
        json={
            "client_name": "ACME Renovation",
            "client_contact": "Alice Martin",
            "client_email": "alice@example.test",
            "client_address": "12 rue des Ateliers, 75001 Paris",
            "validity_days": 21,
            "tax_rate": 20.0,
            "currency": "EUR",
            "lines": [
                {
                    "variant_id": None,
                    "description": "Baie coulissante aluminium",
                    "quantity": 2,
                    "unit_price": 1500.0,
                    "discount_pct": 0,
                    "visual_config": None,
                },
            ],
        },
        headers=headers,
    )
    assert create_response.status_code == 200, create_response.text
    sale = create_response.json()

    with patch("backend.core.events.smtplib.SMTP") as smtp_cls:
        server = smtp_cls.return_value.__enter__.return_value
        sent_response = client.put(
            f"/v2/sales/{sale['id']}/status",
            params={"status": "SENT"},
            headers=headers,
        )
        assert sent_response.status_code == 200, sent_response.text
        portal_link = sent_response.json()["portal_link"]
        token = portal_link.rsplit("/", 1)[-1]
        sign_response = client.post(f"/v2/sales/portal/{token}/sign")
        assert sign_response.status_code == 200, sign_response.text

    assert server.send_message.call_count == 2
    invitation = server.send_message.call_args_list[0][0][0]
    confirmation = server.send_message.call_args_list[1][0][0]
    assert invitation["To"] == "alice@example.test"
    assert "à signer" in invitation["Subject"]
    assert confirmation["To"] == "alice@example.test"
    assert sale["reference"] in confirmation["Subject"]
    plain_part = confirmation.get_payload()[0].get_payload(decode=True).decode("utf-8")
    # 2 × 1500 € HT, TVA 20 % → 3 600,00 € TTC
    assert "3 600,00 € TTC" in plain_part


def test_portal_sign_without_smtp_config_still_signs(isolated_client, monkeypatch):
    """Sans config SMTP, la signature portail aboutit quand même (best-effort)."""
    client, TestingSessionLocal = isolated_client
    _create_admin(TestingSessionLocal)
    headers = _admin_headers(client)
    _clear_smtp_env(monkeypatch)

    create_response = client.post(
        "/v2/sales/",
        json={
            "client_name": "Sans SMTP SARL",
            "client_email": "client@example.test",
            "validity_days": 30,
            "tax_rate": 20.0,
            "currency": "EUR",
            "lines": [
                {
                    "variant_id": None,
                    "description": "Porte d'entrée",
                    "quantity": 1,
                    "unit_price": 900.0,
                    "discount_pct": 0,
                    "visual_config": None,
                },
            ],
        },
        headers=headers,
    )
    assert create_response.status_code == 200, create_response.text
    sale = create_response.json()

    sent_response = client.put(
        f"/v2/sales/{sale['id']}/status",
        params={"status": "SENT"},
        headers=headers,
    )
    assert sent_response.json()["email_status"] == "SKIPPED"
    assert sent_response.json()["email_error"] == "SMTP non configuré."
    token = sent_response.json()["portal_link"].rsplit("/", 1)[-1]

    with patch("backend.core.events.smtplib.SMTP") as smtp_cls:
        sign_response = client.post(f"/v2/sales/portal/{token}/sign")
        assert sign_response.status_code == 200, sign_response.text
    smtp_cls.assert_not_called()

    signed = client.get(f"/v2/sales/{sale['id']}", headers=headers).json()
    assert signed["status"] == "VALIDATED"
    assert signed["signed_at"] is not None
