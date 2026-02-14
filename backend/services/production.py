from sqlalchemy.orm import Session
from datetime import datetime
from .. import models
from ..core.logger import logger

class ProductionService:
    
    @staticmethod
    def get_order(db: Session, reference: str):
        return db.query(models.Order).filter(models.Order.reference == reference).first()

    @staticmethod
    def create_order_if_not_exists(db: Session, reference: str, material: str):
        order = ProductionService.get_order(db, reference)
        if not order:
            logger.info(f"Auto-creating missing order: {reference}")
            order = models.Order(reference=reference, width=0, height=0, material=material)
            db.add(order)
            db.commit()
            db.refresh(order)
        return order

    @staticmethod
    def get_active_log(db: Session, order_id: int, station: str):
        return db.query(models.ProductionLog).filter(
            models.ProductionLog.order_id == order_id,
            models.ProductionLog.station == station,
            models.ProductionLog.end_time.is_(None)
        ).first()

    @staticmethod
    def start_production(db: Session, order_reference: str, station: str, material: str):
        order = ProductionService.create_order_if_not_exists(db, order_reference, material)
        
        active = ProductionService.get_active_log(db, order.id, station)
        if active:
            logger.warning(f"Double start attempt blocked: {order_reference} on {station}")
            return None # Or raise Error
        
        logger.info(f"Starting production: {order_reference} on {station}")
        new_log = models.ProductionLog(
            order_id=order.id,
            station=station,
            material=material,
            start_time=datetime.now()
        )
        db.add(new_log)
        db.commit()
        db.refresh(new_log)
        return new_log

    @staticmethod
    def stop_production(db: Session, order_reference: str, station: str):
        order = ProductionService.get_order(db, order_reference)
        if not order:
            return None
            
        active = ProductionService.get_active_log(db, order.id, station)
        if not active:
            logger.warning(f"Stop attempt on inactive station: {order_reference} on {station}")
            return None
            
        active.end_time = datetime.now()
        active.duration_seconds = int((active.end_time - active.start_time).total_seconds())
        logger.info(f"Stopped production: {order_reference} on {station} - Duration: {active.duration_seconds}s")
        
        db.commit()
        db.refresh(active)
        return active
