import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend import models
from backend.core import security
from backend.core.security import get_password_hash


@pytest.fixture()
def client(isolated_client):
    # Base entièrement en mémoire (fixture `isolated_client` de conftest.py) :
    # le WebSocket /ws/{id} instancie database.SessionLocal() directement,
    # il est donc patché lui aussi — aucune dépendance à ./atelier.db.
    test_client, TestingSessionLocal = isolated_client

    with TestingSessionLocal() as db:
        db.add(
            models.User(
                username="admin",
                pin_hash=get_password_hash("1234"),
                role="ADMIN",
                is_active=True,
            )
        )
        db.add(
            models.User(
                username="operateur",
                pin_hash=get_password_hash("1111"),
                role="OPERATOR",
                is_active=True,
            )
        )
        db.commit()

    return test_client, TestingSessionLocal


def _login(client: TestClient, username: str, password: str) -> dict:
    response = client.post("/token", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_pdf_endpoints_require_authentication(client):
    test_client, _ = client
    responses = [
        test_client.get("/v2/pdf/quote/1"),
        test_client.get("/v2/pdf/invoice/1"),
        test_client.get("/v2/pdf/delivery-note/1"),
    ]
    assert [response.status_code for response in responses] == [401, 401, 401]


def test_token_of_unknown_or_deactivated_user_is_rejected(client):
    test_client, TestingSessionLocal = client

    # Utilisateur inexistant en base
    ghost_token = security.create_access_token({"sub": "fantome", "role": "ADMIN"})
    response = test_client.get(
        "/v2/sales/", headers={"Authorization": f"Bearer {ghost_token}"}
    )
    assert response.status_code == 401

    # Utilisateur désactivé après émission du token
    headers = _login(test_client, "admin", "1234")
    assert test_client.get("/v2/sales/", headers=headers).status_code == 200
    with TestingSessionLocal() as db:
        user = db.query(models.User).filter(models.User.username == "admin").first()
        user.is_active = False
        db.commit()
    response = test_client.get("/v2/sales/", headers=headers)
    assert response.status_code == 401


def test_orders_endpoint_requires_manager_role(client):
    test_client, _ = client
    payload = {"reference": "CMD-SEC-1", "width": 100, "height": 100, "material": "PVC"}

    assert test_client.post("/orders/", json=payload).status_code == 401

    operator_headers = _login(test_client, "operateur", "1111")
    assert test_client.post("/orders/", json=payload, headers=operator_headers).status_code == 403

    admin_headers = _login(test_client, "admin", "1234")
    assert test_client.post("/orders/", json=payload, headers=admin_headers).status_code == 200


def test_upload_rejects_forbidden_extension(client):
    test_client, _ = client
    admin_headers = _login(test_client, "admin", "1234")

    response = test_client.post(
        "/v2/stock/products/upload_image",
        files={"file": ("evil.exe", b"MZ-fake-binary", "application/octet-stream")},
        headers=admin_headers,
    )
    assert response.status_code == 400

    response = test_client.post(
        "/v2/ingest/upload",
        files={"file": ("evil.php", b"<?php echo 1;", "application/octet-stream")},
        headers=admin_headers,
    )
    assert response.status_code == 400

    response = test_client.post(
        "/v2/ingest/upload",
        files={"file": ("image.png", b"not-really-png", "application/x-msdownload")},
        headers=admin_headers,
    )
    assert response.status_code == 400


def test_base64_upload_validation():
    from fastapi import HTTPException
    from backend.core.uploads import MAX_BASE64_PAYLOAD_LENGTH, decode_base64_upload

    content, extension = decode_base64_upload("data:image/png;base64,aGVsbG8=")
    assert content == b"hello"
    assert extension == ".png"

    with pytest.raises(HTTPException):
        decode_base64_upload("data:image/svg+xml;base64,aGVsbG8=")

    with pytest.raises(HTTPException):
        decode_base64_upload("!!!pas-du-base64!!!")

    with pytest.raises(HTTPException):
        decode_base64_upload("A" * (MAX_BASE64_PAYLOAD_LENGTH + 1))


def test_websocket_requires_valid_token(client):
    test_client, _ = client

    with pytest.raises(WebSocketDisconnect):
        with test_client.websocket_connect("/ws/1"):
            pass

    with pytest.raises(WebSocketDisconnect):
        with test_client.websocket_connect("/ws/1?token=token-invalide"):
            pass

    headers = _login(test_client, "admin", "1234")
    token = headers["Authorization"].removeprefix("Bearer ")
    with test_client.websocket_connect(f"/ws/1?token={token}") as websocket:
        websocket.send_text("ping")
        assert websocket.receive_text() == "Client #1 says: ping"
