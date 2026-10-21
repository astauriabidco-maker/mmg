"""Resolve delivery coordinates from the linked commercial/measurement dossier."""

from .. import models


def populate_delivery_details(db, note):
    order = db.get(models.Order, note.order_id) if note.order_id else None
    sale_id = note.sale_order_id or (order.sale_order_id if order else None)
    dossier = None
    if order:
        dossier = db.query(models.MMG).filter(models.MMG.order_id == order.id).first()
        sale_id = sale_id or (dossier.sale_order_id if dossier else None)
    if not dossier and sale_id:
        dossier = db.query(models.MMG).filter(models.MMG.sale_order_id == sale_id).first()
    mission = dossier.measure_mission if dossier else None
    if not mission and sale_id:
        mission = db.query(models.MeasureMission).filter(models.MeasureMission.sale_order_id == sale_id).first()
    site = (mission.site if mission else None) or (dossier.site_location if dossier else None)
    client = (mission.client if mission else None) or (dossier.client if dossier else None)
    sale = db.get(models.SaleOrder, sale_id) if sale_id else None
    note.sale_order_id = sale_id
    # Never overwrite dispatcher corrections or historical delivery coordinates.
    if not (note.delivery_address or "").strip():
        note.delivery_address = (
            (site.formatted_address if site else None)
            or (dossier.site_address if dossier else None)
            or (sale.client_address if sale else None)
            or (client.address if client else None)
            or (dossier.client_address if dossier else None)
        )
    if not (note.contact_phone or "").strip():
        note.contact_phone = (
            (site.contact_phone if site else None)
            or (client.phone if client else None)
        )
    return note
