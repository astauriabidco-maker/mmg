from datetime import timedelta

import pytest

from backend import models
from backend.core import security
from backend.core.time import utcnow


def seed(factory, status="SENT", *, expired=False, signed=False):
    with factory() as db:
        db.add(models.User(username="audit-admin", role="ADMIN", pin_hash="unused", is_active=True))
        sale = models.SaleOrder(
            reference="AUDIT", client_name="Audit isolated", status=status,
            workflow_type="FABRICATION_FROM_MEASURE", signature_token="audit-token",
            created_at=utcnow() - timedelta(days=100) if expired else utcnow(), validity_days=30,
            signed_at=utcnow() if signed else None, tax_rate=20,
        )
        sale.lines = [models.SaleOrderLine(description="Audit", quantity=1, unit_price=100, line_type="SERVICE")]
        db.add(sale)
        db.commit()
        return sale.id


def headers():
    return {"Authorization": "Bearer " + security.create_access_token({"sub": "audit-admin", "role": "ADMIN"})}


@pytest.mark.parametrize("status,expired,expected", [("CANCELLED", False, 409), ("SENT", True, 410), ("DRAFT", False, 409)])
def test_invalid_public_signature_does_not_mutate(isolated_client, status, expired, expected):
    client, factory = isolated_client
    sid = seed(factory, status, expired=expired)
    response = client.post("/v2/sales/portal/audit-token/sign")
    assert response.status_code == expected, response.text
    with factory() as db:
        assert db.get(models.SaleOrder, sid).status == status
        assert db.get(models.SaleOrder, sid).signed_at is None
        assert db.query(models.Invoice).count() == 0


@pytest.mark.parametrize("status", ["VALIDATED", "IN_PRODUCTION", "DELIVERED"])
def test_signed_public_link_is_idempotent_even_after_execution(isolated_client, status):
    client, factory = isolated_client
    sid = seed(factory, status, signed=True, expired=True)
    with factory() as db:
        original_timestamp = db.get(models.SaleOrder, sid).signed_at
    for _ in range(2):
        assert client.post("/v2/sales/portal/audit-token/sign").status_code == 200
    with factory() as db:
        assert db.get(models.SaleOrder, sid).status == status
        assert db.get(models.SaleOrder, sid).signed_at == original_timestamp
        assert db.query(models.Invoice).count() == 0


def test_list_matches_detail_traceability(isolated_client):
    client, factory = isolated_client
    sid = seed(factory, "DELIVERED", signed=True)
    with factory() as db:
        order = models.Order(reference="AUDIT-1", sale_order_id=sid, material=models.MaterialType.PVC)
        db.add(order)
        db.flush()
        db.add(models.DeliveryNote(reference="BL-AUDIT", order_id=order.id, sale_order_id=sid, client_name="Audit", status="DELIVERED"))
        db.add(models.Invoice(reference="F-AUDIT", client_name="Audit isolated", sale_order_id=sid,
            invoice_type="FINAL", status="PAID", subtotal=100, tax_amount=20, total=120))
        db.commit()
    detail = client.get(f"/v2/sales/{sid}", headers=headers()).json()
    listing = client.get("/v2/sales/", headers=headers()).json()[0]
    for field in ("invoices", "delivery_notes", "production_orders", "reservations"):
        assert listing[field] == detail[field]
    assert listing["delivery_notes"][0]["order_id"] == detail["production_orders"][0]["id"]


def test_cancelled_signed_quote_cannot_create_deposit(isolated_client):
    client, factory = isolated_client
    sid = seed(factory, "CANCELLED", signed=True)
    assert client.post(f"/v2/sales/{sid}/create-deposit-invoice", headers=headers()).status_code == 409
    with factory() as db:
        assert db.query(models.Invoice).count() == 0


def test_final_invoice_requires_every_production_delivery(isolated_client):
    client, factory = isolated_client
    sid = seed(factory, "IN_PRODUCTION", signed=True)
    with factory() as db:
        first = models.Order(reference="AUDIT-1", sale_order_id=sid, material=models.MaterialType.PVC)
        second = models.Order(reference="AUDIT-2", sale_order_id=sid, material=models.MaterialType.PVC)
        db.add_all([first, second])
        db.flush()
        db.add(models.DeliveryNote(reference="BL-AUDIT", order_id=first.id, sale_order_id=sid, client_name="Audit", status="DELIVERED"))
        db.add(models.DeliveryNote(reference="BL-AUDIT-2", order_id=second.id, sale_order_id=sid, client_name="Audit", status="IN_TRANSIT"))
        db.commit()
    response = client.post(f"/v2/sales/{sid}/create-final-invoice", headers=headers())
    assert response.status_code == 409, response.text
    with factory() as db:
        assert db.query(models.Invoice).count() == 0
        db.query(models.DeliveryNote).filter_by(reference="BL-AUDIT-2").one().status = "DELIVERED"
        db.commit()
    for _ in range(2):
        assert client.post(f"/v2/sales/{sid}/create-final-invoice", headers=headers()).status_code == 200
    with factory() as db:
        assert db.query(models.Invoice).count() == 1
        assert float(db.query(models.Invoice).one().total) == 120


def test_unsigned_linked_opportunity_can_edit_next_action(isolated_client):
    client, factory = isolated_client
    sid = seed(factory)
    with factory() as db:
        customer = models.Client(name="Audit isolated")
        db.add(customer)
        db.flush()
        opp = models.CRMOpportunity(reference="OPP-AUDIT", client_id=customer.id, title="Audit",
            stage="proposition_envoyee", sale_order_id=sid)
        db.add(opp)
        db.commit()
        oid = opp.id
    response = client.patch(f"/v2/mmg/opportunities/{oid}", headers=headers(), json={"next_milestone": "Relance demain"})
    assert response.status_code == 200, response.text
    assert response.json()["next_milestone"] == "Relance demain"
    assert response.json()["stage"] == "proposition_envoyee"
    assert response.json()["sale_order_id"] == sid
