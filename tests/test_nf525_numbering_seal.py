"""Tests NF525 : numérotation transactionnelle et sceau HMAC chaîné."""
import re
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend import database, models
from backend.core.security import get_password_hash
from backend.main import app
from backend.services import nf525_seal
from backend.services.document_sequences import next_number

TEST_HMAC_KEY = "cle-de-test-nf525-unitaire"
CURRENT_YEAR = datetime.utcnow().year


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("NF525_HMAC_KEY", TEST_HMAC_KEY)

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = override_get_db

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

    try:
        with TestClient(app) as test_client:
            test_client.testing_session_local = TestingSessionLocal
            yield test_client
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def _auth_headers(client: TestClient) -> dict:
    response = client.post("/token", data={"username": "admin", "password": "1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_invoice(client: TestClient, headers: dict, client_name: str = "Client Test", unit_price: float = 100.0) -> dict:
    response = client.post(
        "/v2/accounting/invoices",
        headers=headers,
        json={
            "client_name": client_name,
            "due_date": "2030-01-01T00:00:00",
            "lines": [
                {"description": "Prestation", "quantity": 1, "unit_price": unit_price, "tax_rate": 20.0}
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _expected_seal(invoice_json: dict, previous_seal: str = "") -> str:
    """Recalcule le HMAC attendu côté test (vérifiabilité du sceau)."""
    invoice = SimpleNamespace(
        reference=invoice_json["reference"],
        client_name=invoice_json["client_name"],
        client_siret=invoice_json.get("client_siret"),
        issue_date=datetime.fromisoformat(invoice_json["issue_date"]),
        subtotal=invoice_json["subtotal"],
        tax_amount=invoice_json["tax_amount"],
        total=invoice_json["total"],
    )
    return nf525_seal.compute_seal(invoice, previous_seal)


# --- Numérotation transactionnelle ---

def test_invoice_numbers_are_sequential_and_unique(client: TestClient):
    headers = _auth_headers(client)

    first = _create_invoice(client, headers, client_name="Client A")
    second = _create_invoice(client, headers, client_name="Client B")

    assert first["reference"] == f"F-{CURRENT_YEAR}-0001"
    assert second["reference"] == f"F-{CURRENT_YEAR}-0002"
    assert first["reference"] != second["reference"]


def test_credit_note_has_independent_sequence(client: TestClient):
    headers = _auth_headers(client)

    invoice = _create_invoice(client, headers)
    response = client.post(f"/v2/accounting/invoices/{invoice['id']}/credit_note", headers=headers)
    assert response.status_code == 200, response.text
    credit_note = response.json()

    assert credit_note["reference"] == f"AV-{CURRENT_YEAR}-0001"
    assert re.fullmatch(rf"AV-{CURRENT_YEAR}-\d{{4}}", credit_note["reference"])

    # La séquence factures n'est pas perturbée par l'avoir
    next_invoice = _create_invoice(client, headers)
    assert next_invoice["reference"] == f"F-{CURRENT_YEAR}-0002"


def test_quotes_use_collision_free_sequence(client: TestClient):
    headers = _auth_headers(client)

    references = []
    for index in range(2):
        response = client.post(
            "/v2/sales/",
            headers=headers,
            json={
                "client_name": f"Client Devis {index}",
                "tax_rate": 20.0,
                "lines": [
                    {"description": "Baie vitrée", "quantity": 1, "unit_price": 1200.0, "discount_pct": 0}
                ],
            },
        )
        assert response.status_code == 200, response.text
        references.append(response.json()["reference"])

    # Ancien format DEV-{date-minute} : deux devis dans la même minute entraient
    # en collision. La séquence DEV-YYYY-XXXX garantit l'unicité.
    assert references[0] == f"DEV-{CURRENT_YEAR}-0001"
    assert references[1] == f"DEV-{CURRENT_YEAR}-0002"
    assert len(set(references)) == 2


def test_sequence_bootstraps_from_legacy_references(client: TestClient):
    """Base sans migration (ex. atelier.db de dev) : le compteur s'amorce sur
    le MAX des références existantes — jamais de réémission."""
    session_local = client.testing_session_local
    with session_local() as db:
        db.add(models.Invoice(
            reference=f"F-{CURRENT_YEAR}-0002",
            client_name="Legacy",
            due_date=datetime(2030, 1, 1),
            status="PAID",
            total=100.0,
        ))
        db.commit()

    headers = _auth_headers(client)
    invoice = _create_invoice(client, headers)
    assert invoice["reference"] == f"F-{CURRENT_YEAR}-0003"


def test_sequence_service_is_monotonic_per_kind(client: TestClient):
    session_local = client.testing_session_local
    with session_local() as db:
        assert next_number(db, "purchase_order") == f"PO-{CURRENT_YEAR}-0001"
        assert next_number(db, "purchase_order") == f"PO-{CURRENT_YEAR}-0002"
        # Kinds indépendants
        assert next_number(db, "delivery_note") == f"BL-{CURRENT_YEAR}-0001"
        with pytest.raises(ValueError):
            next_number(db, "kind_inconnu")
        db.commit()

    # Le compteur survit au commit (pas de réémission après une nouvelle session)
    with session_local() as db:
        assert next_number(db, "purchase_order") == f"PO-{CURRENT_YEAR}-0003"


# --- Sceau NF525 (HMAC chaîné) ---

def test_seal_is_verifiable_hmac(client: TestClient):
    headers = _auth_headers(client)
    invoice = _create_invoice(client, headers, client_name="Client HMAC", unit_price=250.0)

    assert invoice["qr_code_hash"]
    # Première pièce : amorce genesis (chaîne vide)
    assert invoice["previous_seal"] in (None, "")
    assert invoice["qr_code_hash"] == _expected_seal(invoice, previous_seal="")


def test_seal_chain_links_to_previous_invoice(client: TestClient):
    headers = _auth_headers(client)

    first = _create_invoice(client, headers, client_name="Client 1")
    second = _create_invoice(client, headers, client_name="Client 2")

    # Chaînage : la facture 2 scelle le sceau de la facture 1
    assert second["previous_seal"] == first["qr_code_hash"]
    assert second["qr_code_hash"] == _expected_seal(second, previous_seal=first["qr_code_hash"])
    assert second["qr_code_hash"] != first["qr_code_hash"]


def test_status_change_does_not_change_seal(client: TestClient):
    headers = _auth_headers(client)
    invoice = _create_invoice(client, headers, unit_price=100.0)  # total = 120.0 TTC
    original_seal = invoice["qr_code_hash"]
    assert invoice["status"] == "UNPAID"

    response = client.post(
        f"/v2/accounting/invoices/{invoice['id']}/pay",
        headers=headers,
        json={"amount": invoice["total"], "method": "VIREMENT"},
    )
    assert response.status_code == 200, response.text
    paid = response.json()

    assert paid["status"] == "PAID"
    # Le sceau porte sur des données immuables : un encaissement ne le change pas
    assert paid["qr_code_hash"] == original_seal
    # ... et il reste vérifiable avec la clé
    assert paid["qr_code_hash"] == _expected_seal(paid, previous_seal="")


def test_seal_excludes_status_from_payload(client: TestClient):
    """Deux pièces identiques hors status produisent le même HMAC."""
    headers = _auth_headers(client)
    invoice = _create_invoice(client, headers, unit_price=100.0)

    clone = SimpleNamespace(
        reference=invoice["reference"],
        client_name=invoice["client_name"],
        client_siret=invoice.get("client_siret"),
        issue_date=datetime.fromisoformat(invoice["issue_date"]),
        subtotal=invoice["subtotal"],
        tax_amount=invoice["tax_amount"],
        total=invoice["total"],
        status="PAID",  # mutable — ne doit pas entrer dans le payload
    )
    assert nf525_seal.compute_seal(clone, "") == invoice["qr_code_hash"]


def test_seal_verification_fails_with_wrong_key(client: TestClient, monkeypatch):
    headers = _auth_headers(client)
    invoice = _create_invoice(client, headers)

    monkeypatch.setenv("NF525_HMAC_KEY", "autre-cle")
    assert _expected_seal(invoice, previous_seal="") != invoice["qr_code_hash"]
