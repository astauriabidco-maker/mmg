from backend import models
from backend.core import security


def test_pos_adjustment_uses_internal_location_when_id_one_is_view(isolated_client):
    client, factory = isolated_client
    with factory() as db:
        db.add(models.User(username="pos-recipe", pin_hash="unused", role="ADMIN", is_active=True))
        db.add(models.StockLocation(id=1, name="Warehouse container", usage="view", is_active=True))
        product = models.Product(reference_base="POS-RECIPE", name="Recipe brush", available_in_pos=True)
        db.add(product)
        db.flush()
        variant = models.ProductVariant(product_id=product.id, reference="POS-RECIPE-STD", quantity_in_stock=0)
        db.add(variant)
        db.commit()
        variant_id = variant.id
    headers = {"Authorization": "Bearer " + security.create_access_token({"sub": "pos-recipe", "role": "ADMIN"})}
    adjusted = client.put(f"/v2/pos/items/{variant_id}?price=1&stock=1", headers=headers)
    assert adjusted.status_code == 200, adjusted.text
    assert adjusted.json()["stock"] == 1
    with factory() as db:
        quant = db.query(models.StockQuant).join(models.StockLocation).filter(
            models.StockQuant.variant_id == variant_id, models.StockLocation.usage == "internal",
        ).one()
        assert quant.quantity == 1
        assert db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=1).first() is None
    opened = client.post('/v2/pos/sessions/open?starting_cash=0', headers=headers)
    assert opened.status_code == 200, opened.text
    session_id = opened.json()['id']
    sold = client.post('/v2/pos/checkout', headers=headers, json={
        'items': [{'variant_id': variant_id, 'quantity': 1, 'price': 1, 'product_name': 'Recipe brush'}],
        'payment_method': 'CB', 'amount_paid': 1, 'seller_name': 'Recipe',
    })
    assert sold.status_code == 200, sold.text
    report = client.get(f'/v2/pos/sessions/{session_id}/report', headers=headers).json()
    assert report['ticket_count'] == 1
    assert report['total_cb_collected'] == 1
    assert report['expected_cash_in_drawer'] == 0
    closed = client.post(f'/v2/pos/sessions/{session_id}/close?closing_cash=0', headers=headers)
    assert closed.status_code == 200, closed.text
