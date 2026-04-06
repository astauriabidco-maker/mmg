from sqlalchemy.orm import Session
from datetime import datetime
from .. import models

class StockService:
    @staticmethod
    def deduct_stock_for_order(db: Session, order_id: int, station_code: str):
        if "DEBIT" not in station_code:
            return

        order = db.query(models.Order).filter(models.Order.id == order_id).first()
        if not order:
            return

        material_str = order.material.value if hasattr(order.material, 'value') else order.material
        base_ref = f"{material_str}-MAIN-PROFILE" 
        
        product = db.query(models.Product).filter(models.Product.reference_base == base_ref).first()
        if not product:
            return

        # V3 PIM: Prendre la première variante du produit
        variant = db.query(models.ProductVariant).filter(models.ProductVariant.product_id == product.id).first()
        if not variant:
            return

        width_m = order.width / 100.0
        height_m = order.height / 100.0
        perimeter_m = (width_m * 2) + (height_m * 2)
        
        quantity_to_deduct = perimeter_m * order.quantity

        variant.quantity_in_stock -= quantity_to_deduct
        
        tx = models.StockTransaction(
            variant_id=variant.id,
            quantity_change=-quantity_to_deduct,
            transaction_type="AUTO_CONSUMPTION",
            order_id=order.id,
            notes=f"Auto-déduction depuis station {station_code} pour CMD {order.reference}"
        )
        db.add(tx)
