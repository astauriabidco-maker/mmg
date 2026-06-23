from sqlalchemy.orm import Session

from .. import models
from .stock_reservations import consume_reservations_for_order


class StockService:
    @staticmethod
    def deduct_stock_for_order(db: Session, order_id: int, station_code: str, author: str = "Système"):
        if "DEBIT" not in station_code.upper():
            return {"created_moves": 0, "consumed_lines": 0, "reservations": 0}

        order = db.query(models.Order).filter(models.Order.id == order_id).first()
        if not order:
            return {"created_moves": 0, "consumed_lines": 0, "reservations": 0}

        return consume_reservations_for_order(db, order.reference, station_code, author=author)
