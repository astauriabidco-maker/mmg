from backend import models
from backend.core import security
from backend.core.security import get_password_hash


def _headers(session_factory, username="ontology-viewer"):
    with session_factory() as db:
        db.add(
            models.User(
                username=username,
                pin_hash=get_password_hash("4826"),
                role="MANAGER",
                is_active=True,
            )
        )
        db.commit()
    token = security.create_access_token(
        {
            "sub": username,
            "role": "MANAGER",
            "permissions": [],
        }
    )
    return {"Authorization": f"Bearer {token}"}


def test_mmg_ontology_api_requires_authentication(isolated_client):
    client, _ = isolated_client

    response = client.get("/v2/mmg/ontology")

    assert response.status_code == 401


def test_mmg_ontology_api_exposes_active_business_reference(isolated_client):
    client, session_factory = isolated_client

    response = client.get("/v2/mmg/ontology", headers=_headers(session_factory))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["pipeline"][0] == "client"
    assert payload["pipeline"][-1] == "real_workshop_debit"
    assert payload["entities"]["crm_opportunity"]["label"] == "Opportunité avant-vente"
    assert payload["model_bindings"]["stock_reservation"] == [
        "StockReservation",
        "StockReservationLine",
    ]
    assert "proposition_a_valider" in {
        item["code"] for item in payload["entity_statuses"]["crm_opportunity"]
    }
    assert "quote_signed" in {item["code"] for item in payload["business_events"]}
    assert {
        ("production_order", "launch", "PRODUCTION_MANAGE"),
        ("real_workshop_debit", "consume", "STOCK_MANAGE"),
    }.issubset(
        {
            (item["entity"], item["action"], item["permission"])
            for item in payload["step_rbac"]
        }
    )
