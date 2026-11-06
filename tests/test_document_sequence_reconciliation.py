from backend import models
from backend.core.time import utcnow
from backend.services.document_sequences import next_number


def test_stale_delivery_sequence_advances_past_existing_notes(isolated_client):
    _, factory = isolated_client
    year = utcnow().year
    with factory() as db:
        db.add(models.DocumentSequence(doc_kind='delivery_note', year=year, counter=1))
        db.add_all([
            models.DeliveryNote(reference=f'BL-{year}-0002', client_name='Existing', status='DELIVERED'),
            models.DeliveryNote(reference=f'BL-{year}-0008', client_name='Imported', status='DELIVERED'),
            models.DeliveryNote(reference=f'BL-{year - 1}-0099', client_name='Previous year', status='DELIVERED'),
        ])
        db.commit()
        assert next_number(db, 'delivery_note', year) == f'BL-{year}-0009'
        assert next_number(db, 'delivery_note', year) == f'BL-{year}-0010'
        db.commit()
        assert db.query(models.DeliveryNote).count() == 3
        assert db.query(models.DeliveryNote).filter_by(reference=f'BL-{year}-0002').one().status == 'DELIVERED'


def test_sequence_never_moves_backwards_when_documents_have_gaps(isolated_client):
    _, factory = isolated_client
    year = utcnow().year
    with factory() as db:
        db.add(models.DocumentSequence(doc_kind='delivery_note', year=year, counter=15))
        db.add(models.DeliveryNote(reference=f'BL-{year}-0008', client_name='Existing', status='DELIVERED'))
        db.commit()
        assert next_number(db, 'delivery_note', year) == f'BL-{year}-0016'
