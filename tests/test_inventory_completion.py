from __future__ import annotations

from datetime import timedelta
from io import BytesIO

import openpyxl

from backend import models
from backend.core import security
from backend.core.time import utcnow


def _headers(
    session_factory,
    username: str,
    role_name: str,
    permissions: list[str],
) -> dict:
    with session_factory() as db:
        permission_rows = []
        for code in permissions:
            permission = db.query(models.Permission).filter_by(code=code).first()
            if not permission:
                permission = models.Permission(
                    code=code,
                    module="Inventaire",
                    description=code,
                )
                db.add(permission)
                db.flush()
            permission_rows.append(permission)
        role = db.query(models.Role).filter_by(name=role_name).first()
        if not role:
            role = models.Role(name=role_name, description=role_name)
            db.add(role)
        role.permissions = permission_rows
        user = db.query(models.User).filter_by(username=username).first()
        if not user:
            user = models.User(
                username=username,
                pin_hash="test-pin",
                role=role_name,
                is_active=True,
            )
            db.add(user)
        db.commit()
    token = security.create_access_token({"sub": username, "role": role_name})
    return {"Authorization": f"Bearer {token}"}


def _seed_inventory_data(session_factory):
    with session_factory() as db:
        product = models.Product(
            reference_base="INV-COMPLETE",
            name="Article inventaire complet",
            material_type="ALU",
            unit="barre",
            supplier="MMG",
            product_type="stockable",
            catalog_status="ACTIVE",
        )
        variant = models.ProductVariant(
            product=product,
            reference="INV-COMPLETE-001",
            barcode="INV000001",
            supplier_reference="FOU-INV-001",
            cost_price=25,
            quantity_in_stock=13,
        )
        counted_location = models.StockLocation(
            name="WH/Inventaire complet",
            usage="internal",
            is_active=True,
        )
        outside_location = models.StockLocation(
            name="WH/Hors campagne",
            usage="internal",
            is_active=True,
        )
        db.add_all([product, counted_location, outside_location])
        db.flush()
        db.add_all([
            models.StockQuant(
                variant_id=variant.id,
                location_id=counted_location.id,
                quantity=10,
            ),
            models.StockQuant(
                variant_id=variant.id,
                location_id=outside_location.id,
                quantity=3,
            ),
        ])
        db.commit()
        return variant.id, counted_location.id, outside_location.id


def _create_session(client, headers, location_id: int, **overrides) -> dict:
    payload = {
        "name": "Campagne inventaire complète",
        "location_id": location_id,
    }
    payload.update(overrides)
    response = client.post(
        "/v2/stock/inventory-sessions",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_blind_counter_cannot_read_expected_stock_and_assignment_is_enforced(
    isolated_client,
):
    client, session_factory = isolated_client
    admin = _headers(session_factory, "inventory-admin", "ADMIN", [])
    counter = _headers(
        session_factory,
        "counter-assigned",
        "MAGASINIER",
        ["STOCK_VIEW", "inventory.count"],
    )
    outsider = _headers(
        session_factory,
        "counter-outsider",
        "MAGASINIER_OUT",
        ["STOCK_VIEW", "inventory.count"],
    )
    variant_id, location_id, outside_id = _seed_inventory_data(session_factory)
    session = _create_session(
        client,
        admin,
        location_id,
        blind_counting=True,
        assigned_usernames=["counter-assigned"],
    )
    line = session["lines"][0]

    counters = client.get("/v2/stock/inventory-counters", headers=admin)
    assert counters.status_code == 200, counters.text
    assert {
        item["username"] for item in counters.json()
    }.issuperset({"counter-assigned", "counter-outsider"})

    products = client.get("/v2/stock/products", headers=counter)
    assert products.status_code == 200, products.text
    variant = products.json()[0]["variants"][0]
    assert variant["quantity_in_stock"] is None
    assert variant["reserved_quantity"] is None
    assert variant["available_quantity"] is None

    quants = client.get("/v2/stock/quants", headers=counter)
    assert quants.status_code == 200, quants.text
    locations = {quant["location_id"] for quant in quants.json()}
    assert location_id not in locations
    assert outside_id in locations

    forbidden = client.post(
        f"/v2/stock/inventory-sessions/{session['id']}/lines",
        headers=outsider,
        json={
            "variant_id": variant_id,
            "location_id": location_id,
            "counted_quantity": 9,
            "expected_version": line["version"],
        },
    )
    assert forbidden.status_code == 403, forbidden.text

    counted = client.post(
        f"/v2/stock/inventory-sessions/{session['id']}/lines",
        headers=counter,
        json={
            "variant_id": variant_id,
            "location_id": location_id,
            "counted_quantity": 9,
            "expected_version": line["version"],
            "client_operation_id": "blind-count-operation-001",
            "reason": "Écart aveugle",
        },
    )
    assert counted.status_code == 200, counted.text
    assert counted.json()["expected_quantity"] is None
    assert counted.json()["variance_value"] is None
    assert counted.json()["status"] == "counted"

    blind_session = client.get(
        f"/v2/stock/inventory-sessions/{session['id']}",
        headers=counter,
    )
    assert blind_session.status_code == 200, blind_session.text
    assert blind_session.json()["total_variance_value"] is None
    assert blind_session.json()["absolute_variance_value"] is None


def test_count_line_version_idempotency_and_attachment(
    isolated_client,
    monkeypatch,
    tmp_path,
):
    client, session_factory = isolated_client
    monkeypatch.chdir(tmp_path)
    admin = _headers(session_factory, "inventory-version-admin", "ADMIN", [])
    variant_id, location_id, _outside_id = _seed_inventory_data(session_factory)
    session = _create_session(client, admin, location_id)
    line = session["lines"][0]
    payload = {
        "variant_id": variant_id,
        "location_id": location_id,
        "counted_quantity": 8,
        "expected_version": line["version"],
        "client_operation_id": "offline-operation-0001",
        "reason": "Casse constatée",
    }
    first = client.post(
        f"/v2/stock/inventory-sessions/{session['id']}/lines",
        headers=admin,
        json=payload,
    )
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 2
    assert first.json()["variance_value"] == -50

    replay = client.post(
        f"/v2/stock/inventory-sessions/{session['id']}/lines",
        headers=admin,
        json=payload,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == first.json()["id"]
    assert replay.json()["version"] == 2

    stale = client.post(
        f"/v2/stock/inventory-sessions/{session['id']}/lines",
        headers=admin,
        json={
            **payload,
            "client_operation_id": "offline-operation-0002",
            "expected_version": 1,
        },
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"]["current_version"] == 2

    attachment = client.post(
        (
            f"/v2/stock/inventory-sessions/{session['id']}/lines/"
            f"{first.json()['id']}/attachments"
        ),
        headers=admin,
        files={"file": ("preuve.jpg", b"fake-image", "image/jpeg")},
    )
    assert attachment.status_code == 200, attachment.text
    assert attachment.json()["filename"] == "preuve.jpg"
    stored = tmp_path / attachment.json()["url"].lstrip("/")
    assert stored.read_bytes() == b"fake-image"


def test_value_approval_cycle_scheduling_and_financial_export(isolated_client):
    client, session_factory = isolated_client
    admin = _headers(session_factory, "inventory-cycle-admin", "ADMIN", [])
    finance = _headers(
        session_factory,
        "inventory-finance",
        "FINANCE",
        ["inventory.approve_value"],
    )
    variant_id, location_id, _outside_id = _seed_inventory_data(session_factory)
    session = _create_session(
        client,
        admin,
        location_id,
        inventory_type="cycle",
        cycle_frequency_days=7,
        approval_threshold_value=10,
    )
    line = session["lines"][0]
    counted = client.post(
        f"/v2/stock/inventory-sessions/{session['id']}/lines",
        headers=admin,
        json={
            "variant_id": variant_id,
            "location_id": location_id,
            "counted_quantity": 8,
            "expected_version": line["version"],
            "reason": "Écart valorisé",
        },
    )
    assert counted.status_code == 200, counted.text
    assert counted.json()["variance_value"] == -50

    submitted = client.post(
        f"/v2/stock/inventory-sessions/{session['id']}/validate",
        headers=admin,
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "pending_approval"
    assert submitted.json()["requires_finance_approval"] is True

    approved = client.post(
        f"/v2/stock/inventory-sessions/{session['id']}/approve-value",
        headers=finance,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["finance_approved_by"] == "inventory-finance"
    assert approved.json()["requires_finance_approval"] is False

    validated = client.post(
        f"/v2/stock/inventory-sessions/{session['id']}/validate",
        headers=admin,
    )
    assert validated.status_code == 200, validated.text
    assert validated.json()["status"] == "validated"

    page = client.get(
        "/v2/stock/inventory-sessions-page?status=scheduled&limit=10",
        headers=admin,
    )
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 1
    next_cycle = page.json()["items"][0]
    assert next_cycle["inventory_type"] == "cycle"
    assert next_cycle["zone_locked"] is False
    assert next_cycle["scheduled_for"] is not None

    report = client.get(
        f"/v2/stock/inventory-sessions/{session['id']}/export",
        headers=admin,
    )
    assert report.status_code == 200, report.text
    workbook = openpyxl.load_workbook(BytesIO(report.content), data_only=True)
    values = [
        cell.value
        for row in workbook.active.iter_rows()
        for cell in row
        if cell.value is not None
    ]
    assert "Écart valorisé net" in values
    assert "Coût unitaire" in values
    assert "Écart valorisé" in values
    assert "inventory-finance" in values


def test_scheduled_campaign_start_archive_restore_and_pagination(isolated_client):
    client, session_factory = isolated_client
    admin = _headers(session_factory, "inventory-history-admin", "ADMIN", [])
    _variant_id, location_id, _outside_id = _seed_inventory_data(session_factory)
    scheduled = _create_session(
        client,
        admin,
        location_id,
        name="Cycle planifié unique",
        scheduled_for=(utcnow() + timedelta(days=1)).isoformat(),
        include_all_variants=True,
    )
    assert scheduled["status"] == "scheduled"
    assert scheduled["zone_locked"] is False
    assert scheduled["lines"] == []

    started = client.post(
        f"/v2/stock/inventory-sessions/{scheduled['id']}/start",
        headers=admin,
    )
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "draft"
    assert started.json()["zone_locked"] is True
    assert len(started.json()["lines"]) == 1

    cancelled = client.post(
        f"/v2/stock/inventory-sessions/{scheduled['id']}/cancel",
        headers=admin,
    )
    assert cancelled.status_code == 200, cancelled.text
    archived = client.post(
        f"/v2/stock/inventory-sessions/{scheduled['id']}/archive",
        headers=admin,
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived_at"] is not None

    hidden = client.get(
        "/v2/stock/inventory-sessions-page?search=Cycle%20planifi%C3%A9&limit=1",
        headers=admin,
    )
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["total"] == 0

    visible = client.get(
        (
            "/v2/stock/inventory-sessions-page"
            "?search=Cycle%20planifi%C3%A9&include_archived=true&limit=1&offset=0"
        ),
        headers=admin,
    )
    assert visible.status_code == 200, visible.text
    assert visible.json()["total"] == 1
    assert visible.json()["items"][0]["id"] == scheduled["id"]

    restored = client.post(
        f"/v2/stock/inventory-sessions/{scheduled['id']}/restore",
        headers=admin,
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["archived_at"] is None
