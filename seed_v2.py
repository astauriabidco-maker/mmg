from backend.database import SessionLocal
from backend import models
from datetime import datetime

def seed():
    db = SessionLocal()
    
    # Create Orders
    orders = [
        {"ref": "CMD-601", "mat": "PVC", "w": 100, "h": 200},
        {"ref": "CMD-602", "mat": "ALU", "w": 120, "h": 210},
        {"ref": "CMD-603", "mat": "PVC", "w": 0.80, "h": 0.60},
    ]
    
    db_orders = []
    for o in orders:
        existing = db.query(models.Order).filter(models.Order.reference == o["ref"]).first()
        if not existing:
            new_order = models.Order(reference=o["ref"], material=o["mat"], width=o["w"], height=o["h"])
            db.add(new_order)
            db.commit()
            db.refresh(new_order)
            db_orders.append(new_order)
        else:
            db_orders.append(existing)

    # Create Users
    users = [
        ("admin", "1234", models.UserRole.ADMIN, None),
        ("manager", "0000", models.UserRole.ADMIN, None),
        ("op_debit", "1111", models.UserRole.OPERATOR, models.StationName.PVC_DEBIT),
        ("op_soudure", "2222", models.UserRole.OPERATOR, models.StationName.PVC_SOUDURE),
        ("op_assemblage", "3333", models.UserRole.OPERATOR, models.StationName.PVC_ASSEMBLAGE)
    ]

    # Create Planning Items (PVC_DEBIT)
    station = models.StationName.PVC_DEBIT
    
    for i, order in enumerate(db_orders):
        plan = models.Planning(
            order_id=order.id,
            station=station,
            priority=10 - i, # Descending priority
            status=models.PlanningStatus.PENDING
        )
        db.add(plan)
    
    db.commit()
    print("Seeded 3 orders into Planning for PVC_DEBIT")
    db.close()

if __name__ == "__main__":
    seed()
