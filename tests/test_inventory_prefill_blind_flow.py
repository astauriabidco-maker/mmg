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
        db.add(models.User(username="inventory-tester", pin_hash="test-pin", role="ADMIN", is_active=True))
        db.commit()
    token = security.create_access_token({"sub": "inventory-tester", "role": "ADMIN"})
    return TestClient(app), TestingSessionLocal, engine, {"Authorization": f"Bearer {token}"}


def _create_product(client, headers, reference_base, variants):
    response = client.post(
        "/v2/stock/products",
        headers=headers,
        json={
            "reference_base": reference_base,
            "name": f"Produit {reference_base}",
            "material_type": "ALU",
            "unit": "barre",
            "supplier": "MMG",
            "variants": variants,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["variants"]


def _create_location(client, headers, name, usage="internal", parent_id=None):
    payload = {"name": name, "usage": usage}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    response = client.post("/v2/stock/locations", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _add_stock(client, headers, variant_id, location_id, quantity):
    response = client.post(
        "/v2/stock/transaction",
        headers=headers,
        json={"variant_id": variant_id, "location_dest_id": location_id, "quantity": quantity},
    )
    assert response.status_code == 200, response.text


def _create_session(client, headers, **overrides):
    payload = {"name": "Campagne test"}
    payload.update(overrides)
    response = client.post("/v2/stock/inventory-sessions", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _count_line(client, headers, session_id, variant_id, location_id, counted, reason=None):
    response = client.post(
        f"/v2/stock/inventory-sessions/{session_id}/lines",
        headers=headers,
        json={
            "variant_id": variant_id,
            "location_id": location_id,
            "counted_quantity": counted,
            "reason": reason,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_prefill_lines_from_zone_quants_including_children():
    client, TestingSessionLocal, engine, headers = _client_with_db()
    try:
        variant_a = _create_product(client, headers, "PREFILL-A", [{"reference": "PREFILL-A-001", "quantity_in_stock": 0}])[0]
        variant_b = _create_product(client, headers, "PREFILL-B", [{"reference": "PREFILL-B-001", "quantity_in_stock": 0}])[0]
        variant_c = _create_product(client, headers, "PREFILL-C", [{"reference": "PREFILL-C-001", "quantity_in_stock": 0}])[0]

        parent_id = _create_location(client, headers, "WH/Zone Parent")
        child_id = _create_location(client, headers, "WH/Zone Parent/Rack 1", parent_id=parent_id)
        outside_id = _create_location(client, headers, "WH/Hors Zone")

        _add_stock(client, headers, variant_a["id"], parent_id, 10)
        _add_stock(client, headers, variant_b["id"], child_id, 5)
        _add_stock(client, headers, variant_c["id"], outside_id, 3)

        session = _create_session(client, headers, name="Comptage zone", location_id=parent_id)
        session_id = session["id"]
        lines = session["lines"]
        assert len(lines) == 2
        by_variant = {line["variant_id"]: line for line in lines}
        assert by_variant[variant_a["id"]]["location_id"] == parent_id
        assert by_variant[variant_a["id"]]["expected_quantity"] == 10.0
        assert by_variant[variant_a["id"]]["status"] == "pending"
        assert by_variant[variant_a["id"]]["counted_quantity"] is None
        assert by_variant[variant_b["id"]]["location_id"] == child_id
        assert by_variant[variant_b["id"]]["expected_quantity"] == 5.0
        assert by_variant[variant_b["id"]]["status"] == "pending"
        assert variant_c["id"] not in by_variant

        # La validation est bloquée tant que des lignes pré-remplies ne sont pas comptées.
        blocked = client.post(f"/v2/stock/inventory-sessions/{session_id}/validate", headers=headers)
        assert blocked.status_code == 400, blocked.text
        assert "restent à compter" in blocked.json()["detail"]

        # Hors zone : le comptage d'un emplacement extérieur est refusé.
        out_of_zone = client.post(
            f"/v2/stock/inventory-sessions/{session_id}/lines",
            headers=headers,
            json={"variant_id": variant_c["id"], "location_id": outside_id, "counted_quantity": 3},
        )
        assert out_of_zone.status_code == 400, out_of_zone.text
        assert "autre emplacement" in out_of_zone.json()["detail"]

        # Comptage des deux lignes (l'emplacement enfant est accepté).
        line_a = _count_line(client, headers, session_id, variant_a["id"], parent_id, 7, reason="Casse constatée")
        assert line_a["expected_quantity"] == 10.0
        assert line_a["variance_quantity"] == -3.0
        assert line_a["status"] == "variance"
        line_b = _count_line(client, headers, session_id, variant_b["id"], child_id, 5)
        assert line_b["status"] == "ok"

        validated = client.post(f"/v2/stock/inventory-sessions/{session_id}/validate", headers=headers)
        assert validated.status_code == 200, validated.text
        assert validated.json()["status"] == "validated"

        with TestingSessionLocal() as db:
            quant_a = db.query(models.StockQuant).filter_by(variant_id=variant_a["id"], location_id=parent_id).one()
            quant_c = db.query(models.StockQuant).filter_by(variant_id=variant_c["id"], location_id=outside_id).one()
        assert quant_a.quantity == 7.0
        assert quant_c.quantity == 3.0
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_include_all_variants_adds_zero_expected_lines():
    client, TestingSessionLocal, engine, headers = _client_with_db()
    try:
        variant_x = _create_product(client, headers, "ALLVAR-X", [{"reference": "ALLVAR-X-001", "quantity_in_stock": 0}])[0]
        variant_y = _create_product(client, headers, "ALLVAR-Y", [{"reference": "ALLVAR-Y-001", "quantity_in_stock": 0}])[0]
        location_id = _create_location(client, headers, "WH/AllVariants")
        _add_stock(client, headers, variant_x["id"], location_id, 4)

        # Par défaut : seules les variantes avec stock dans la zone sont pré-remplies.
        default_session = _create_session(client, headers, name="Sans option", location_id=location_id)
        assert [line["variant_id"] for line in default_session["lines"]] == [variant_x["id"]]

        # Avec l'option : la variante sans stock apparaît avec un espéré de 0.
        session = _create_session(
            client, headers, name="Avec option", location_id=location_id, include_all_variants=True
        )
        session_id = session["id"]
        by_variant = {line["variant_id"]: line for line in session["lines"]}
        assert set(by_variant) == {variant_x["id"], variant_y["id"]}
        assert by_variant[variant_y["id"]]["expected_quantity"] == 0.0
        assert by_variant[variant_y["id"]]["location_id"] == location_id
        assert by_variant[variant_y["id"]]["status"] == "pending"

        # L'oubli est détecté : l'opérateur doit trancher explicitement (ici 0 constaté).
        _count_line(client, headers, session_id, variant_x["id"], location_id, 4)
        line_y = _count_line(client, headers, session_id, variant_y["id"], location_id, 0)
        assert line_y["status"] == "ok"

        validated = client.post(f"/v2/stock/inventory-sessions/{session_id}/validate", headers=headers)
        assert validated.status_code == 200, validated.text
        assert validated.json()["status"] == "validated"
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_blind_counting_masks_expected_until_validation():
    client, TestingSessionLocal, engine, headers = _client_with_db()
    try:
        variant = _create_product(client, headers, "BLIND-PROD", [{"reference": "BLIND-PROD-001", "quantity_in_stock": 0}])[0]
        location_id = _create_location(client, headers, "WH/Aveugle")
        _add_stock(client, headers, variant["id"], location_id, 10)

        session = _create_session(
            client, headers, name="Comptage aveugle", location_id=location_id, blind_counting=True
        )
        session_id = session["id"]
        assert session["blind_counting"] is True
        assert session["lines"][0]["expected_quantity"] is None
        assert session["lines"][0]["variance_quantity"] is None

        # L'espéré reste masqué sur la réponse de comptage et la relecture.
        line = _count_line(client, headers, session_id, variant["id"], location_id, 8, reason="Écart aveugle")
        assert line["expected_quantity"] is None
        assert line["variance_quantity"] is None
        assert line["counted_quantity"] == 8.0

        fetched = client.get(f"/v2/stock/inventory-sessions/{session_id}", headers=headers)
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["lines"][0]["expected_quantity"] is None
        assert fetched.json()["lines"][0]["variance_quantity"] is None

        listed = client.get("/v2/stock/inventory-sessions", headers=headers)
        assert listed.status_code == 200, listed.text
        listed_session = next(item for item in listed.json() if item["id"] == session_id)
        assert listed_session["lines"][0]["expected_quantity"] is None

        # La validation calcule les écarts côté serveur et l'espéré redevient visible.
        validated = client.post(f"/v2/stock/inventory-sessions/{session_id}/validate", headers=headers)
        assert validated.status_code == 200, validated.text
        validated_line = validated.json()["lines"][0]
        assert validated_line["expected_quantity"] == 10.0
        assert validated_line["variance_quantity"] == -2.0
        assert validated_line["status"] == "validated"

        with TestingSessionLocal() as db:
            quant = db.query(models.StockQuant).filter_by(variant_id=variant["id"], location_id=location_id).one()
        assert quant.quantity == 8.0
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_double_validation_returns_409():
    client, TestingSessionLocal, engine, headers = _client_with_db()
    try:
        variant = _create_product(client, headers, "DOUBLE-PROD", [{"reference": "DOUBLE-PROD-001", "quantity_in_stock": 0}])[0]
        location_id = _create_location(client, headers, "WH/Double Validation")
        _add_stock(client, headers, variant["id"], location_id, 3)

        session = _create_session(client, headers, name="Double validation", location_id=location_id)
        session_id = session["id"]
        _count_line(client, headers, session_id, variant["id"], location_id, 3)

        first = client.post(f"/v2/stock/inventory-sessions/{session_id}/validate", headers=headers)
        assert first.status_code == 200, first.text
        assert first.json()["status"] == "validated"

        second = client.post(f"/v2/stock/inventory-sessions/{session_id}/validate", headers=headers)
        assert second.status_code == 409, second.text
        assert "déjà validée" in second.json()["detail"]
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_zone_locked_defaults_true_server_side():
    client, TestingSessionLocal, engine, headers = _client_with_db()
    try:
        location_id = _create_location(client, headers, "WH/Gel Défaut")

        # Sans mention de zone_locked : le gel est imposé côté serveur.
        default_session = _create_session(client, headers, name="Gel par défaut", location_id=location_id)
        assert default_session["zone_locked"] is True

        # Le client peut explicitement demander False (garde anti-dérive 409 conservée).
        unlocked_session = _create_session(
            client, headers, name="Gel désactivé", location_id=location_id, zone_locked=False
        )
        assert unlocked_session["zone_locked"] is False
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)
