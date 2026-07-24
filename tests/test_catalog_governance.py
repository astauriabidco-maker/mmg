from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import database, models
from backend.core import security
from backend.main import app


def _client_with_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = override_get_db
    with testing_session() as db:
        db.add(models.User(username="catalog-admin", pin_hash="test", role="ADMIN", is_active=True))
        db.commit()
    token = security.create_access_token({"sub": "catalog-admin", "role": "ADMIN"})
    return TestClient(app), engine, {"Authorization": f"Bearer {token}"}


def _draft_payload(reference="CAT-GOV-001", barcode="370000000001"):
    return {
        "reference_base": reference,
        "name": "Profil de test gouvernance",
        "category": "PROFIL",
        "material_type": "ALU",
        "unit": "barre",
        "supplier": "FOURNISSEUR TEST",
        "product_type": "stockable",
        "catalog_status": "DRAFT",
        "variants": [
            {
                "reference": f"{reference}-BLANC",
                "barcode": barcode,
                "color": "RAL 9016",
                "finish": "Laqué",
                "conditioning": "Botte",
                "units_per_package": 10,
                "cost_price": 20,
            }
        ],
    }


def test_catalog_lifecycle_requires_qualification_and_complete_variant():
    client, engine, headers = _client_with_db()
    try:
        created = client.post("/v2/stock/products", headers=headers, json=_draft_payload())
        assert created.status_code == 200, created.text
        product = created.json()
        product_id = product["id"]
        variant_id = product["variants"][0]["id"]
        assert product["catalog_status"] == "DRAFT"
        assert product["variants"][0]["finish"] == "Laqué"
        assert product["variants"][0]["units_per_package"] == 10

        direct_activation = client.post(
            f"/v2/stock/products/{product_id}/status",
            headers=headers,
            json={"status": "ACTIVE"},
        )
        assert direct_activation.status_code == 409

        to_qualify = client.post(
            f"/v2/stock/products/{product_id}/status",
            headers=headers,
            json={"status": "TO_QUALIFY"},
        )
        assert to_qualify.status_code == 200, to_qualify.text

        incomplete_activation = client.post(
            f"/v2/stock/products/{product_id}/status",
            headers=headers,
            json={"status": "ACTIVE"},
        )
        assert incomplete_activation.status_code == 422
        assert "référence fournisseur" in incomplete_activation.json()["detail"]
        assert "longueur" in incomplete_activation.json()["detail"]

        variant = product["variants"][0]
        variant.update(
            {
                "supplier_reference": "FOUR-001",
                "length_per_unit": 6.5,
                "quantity_in_stock": 0,
            }
        )
        updated_variant = client.put(
            f"/v2/stock/variants/{variant_id}",
            headers=headers,
            json=variant,
        )
        assert updated_variant.status_code == 200, updated_variant.text

        activated = client.post(
            f"/v2/stock/products/{product_id}/status",
            headers=headers,
            json={"status": "ACTIVE"},
        )
        assert activated.status_code == 200, activated.text
        assert activated.json()["catalog_status"] == "ACTIVE"

        no_reason = client.post(
            f"/v2/stock/products/{product_id}/status",
            headers=headers,
            json={"status": "BLOCKED"},
        )
        assert no_reason.status_code == 422

        blocked = client.post(
            f"/v2/stock/products/{product_id}/status",
            headers=headers,
            json={"status": "BLOCKED", "reason": "Référence suspendue par le fournisseur"},
        )
        assert blocked.status_code == 200, blocked.text

        history = client.get(f"/v2/stock/products/{product_id}/history", headers=headers)
        assert history.status_code == 200, history.text
        actions = [entry["action"] for entry in history.json()]
        assert "PRODUCT_CREATED" in actions
        assert "VARIANT_UPDATED" in actions
        assert actions.count("STATUS_CHANGED") >= 3
        assert all(entry["author"] == "catalog-admin" for entry in history.json())
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_catalog_rejects_duplicate_family_variant_barcode_and_supplier_reference():
    client, engine, headers = _client_with_db()
    try:
        first = client.post("/v2/stock/products", headers=headers, json=_draft_payload())
        assert first.status_code == 200, first.text

        duplicate_family = client.post(
            "/v2/stock/products",
            headers=headers,
            json=_draft_payload(reference="cat-gov-001", barcode="370000000002"),
        )
        assert duplicate_family.status_code == 409

        duplicate_variant_payload = _draft_payload(reference="CAT-GOV-002", barcode="370000000002")
        duplicate_variant_payload["variants"][0]["reference"] = "CAT-GOV-001-BLANC"
        duplicate_variant = client.post(
            "/v2/stock/products",
            headers=headers,
            json=duplicate_variant_payload,
        )
        assert duplicate_variant.status_code == 409

        first_variant = first.json()["variants"][0]
        first_variant.update({"supplier_reference": "FOUR-UNIQUE", "quantity_in_stock": 0})
        updated = client.put(
            f"/v2/stock/variants/{first_variant['id']}",
            headers=headers,
            json=first_variant,
        )
        assert updated.status_code == 200, updated.text

        duplicate_supplier_payload = _draft_payload(reference="CAT-GOV-003", barcode="370000000003")
        duplicate_supplier_payload["variants"][0]["supplier_reference"] = "four-unique"
        duplicate_supplier = client.post(
            "/v2/stock/products",
            headers=headers,
            json=duplicate_supplier_payload,
        )
        assert duplicate_supplier.status_code == 409

        duplicate_barcode_payload = _draft_payload(reference="CAT-GOV-004", barcode="370000000001")
        duplicate_barcode = client.post(
            "/v2/stock/products",
            headers=headers,
            json=duplicate_barcode_payload,
        )
        assert duplicate_barcode.status_code == 409
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
