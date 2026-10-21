from backend import models
from backend.core import security
from backend.services.delivery_details import populate_delivery_details


def seed(factory):
    with factory() as db:
        db.add(models.User(username="dispatcher", pin_hash="unused", role="ADMIN", is_active=True))
        client = models.Client(name="Recipe client", address="Billing street", phone="0100000000")
        sale = models.SaleOrder(reference="DEV-RECIPE", client_name=client.name, client_address="Invoice street", status="IN_PRODUCTION")
        db.add_all([client, sale])
        db.flush()
        site = models.ClientSiteAddress(reference="CH-RECIPE", client_id=client.id, address_line1="Site street", postal_code="75020", city="Paris", contact_phone="0200000000")
        order = models.Order(reference="PROD-RECIPE", sale_order_id=sale.id, material=models.MaterialType.PVC)
        db.add_all([site, order])
        db.flush()
        db.add(models.MeasureMission(reference="MET-RECIPE", client_id=client.id, site_address_id=site.id, sale_order_id=sale.id))
        note = models.DeliveryNote(reference="BL-RECIPE", order_id=order.id, client_name=client.name, status="READY")
        db.add(note)
        db.commit()
        return note.id, sale.id


def headers():
    return {"Authorization": "Bearer " + security.create_access_token({"sub": "dispatcher", "role": "ADMIN"})}


def test_coordinates_from_site_and_manual_values_preserved(isolated_client):
    _, factory = isolated_client
    note_id, sale_id = seed(factory)
    with factory() as db:
        note = populate_delivery_details(db, db.get(models.DeliveryNote, note_id))
        assert note.sale_order_id == sale_id
        assert note.delivery_address == "Site street, 75020 Paris, FR"
        assert note.contact_phone == "0200000000"
        note.delivery_address = "Dispatcher override"
        populate_delivery_details(db, note)
        assert note.delivery_address == "Dispatcher override"


def test_repair_legacy_note_route_and_delivery(isolated_client):
    client, factory = isolated_client
    note_id, sale_id = seed(factory)
    payload = {"driver_name": "Recipe driver", "vehicle": "Recipe van", "planned_date": "2026-10-21T00:00:00", "note_ids": [note_id]}
    assert client.post("/v2/logistics/routes", json=payload, headers=headers()).status_code == 400
    repaired = client.patch(f"/v2/logistics/notes/{note_id}", json={"restore_from_source": True}, headers=headers())
    assert repaired.status_code == 200, repaired.text
    assert repaired.json()["contact_phone"] == "0200000000"
    assert repaired.json()["sale_order_id"] == sale_id
    created = client.post("/v2/logistics/routes", json=payload, headers=headers())
    assert created.status_code == 200, created.text
    assert created.json()["notes"][0]["status"] == "ASSIGNED"
    assert client.post("/v2/logistics/routes", json=payload, headers=headers()).status_code == 409
    route_id = created.json()["id"]
    assert client.post(f"/v2/logistics/routes/{route_id}/start", headers=headers()).status_code == 200
    assert client.patch(f"/v2/logistics/notes/{note_id}", json={"delivery_address": "Other"}, headers=headers()).status_code == 409
    assert client.post(f"/v2/logistics/notes/{note_id}/deliver", headers=headers()).status_code == 200
    with factory() as db:
        assert db.get(models.SaleOrder, sale_id).status == "DELIVERED"
        assert db.get(models.DeliveryRoute, route_id).status == "COMPLETED"


def test_client_fallback_and_partial_delivery(isolated_client):
    client, factory = isolated_client
    note_id, sale_id = seed(factory)
    with factory() as db:
        mission = db.query(models.MeasureMission).one()
        mission.site_address_id = None
        sale = db.get(models.SaleOrder, sale_id)
        sale.client_address = None
        note = populate_delivery_details(db, db.get(models.DeliveryNote, note_id))
        assert note.delivery_address == "Billing street"
        assert note.contact_phone == "0100000000"
        db.add(models.Order(reference="PROD-SECOND", sale_order_id=sale_id, material=models.MaterialType.PVC))
        db.commit()
    client.post(f"/v2/logistics/notes/{note_id}/deliver", headers=headers())
    with factory() as db:
        assert db.get(models.SaleOrder, sale_id).status == "IN_PRODUCTION"
