from backend.database import SessionLocal
from backend import models
from datetime import datetime, timedelta
import random
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def seed_scenario():
    db = SessionLocal()
    
    # 1. Clear Data (Optional, but cleaner for scenario)
    # db.query(models.ProductionLog).delete()
    # db.query(models.Planning).delete()
    # db.query(models.Order).delete()
    # db.query(models.User).delete()
    # db.commit()

    print("--- Seeding V3 Scenario ---")

    # 2. Users (Admin, Manager, Operators)
    users = [
        ("admin", "1234", models.UserRole.ADMIN, None),
        ("manager", "0000", models.UserRole.ADMIN, None),
        ("op_debit", "1111", models.UserRole.OPERATOR, models.StationName.PVC_DEBIT),
        ("op_soudure", "2222", models.UserRole.OPERATOR, models.StationName.PVC_SOUDURE),
        ("op_assemblage", "3333", models.UserRole.OPERATOR, models.StationName.PVC_ASSEMBLAGE),
        ("op_vitrage", "4444", models.UserRole.OPERATOR, models.StationName.PVC_VITRAGE),
    ]
    
    for username, pin, role, station in users:
        if not db.query(models.User).filter(models.User.username == username).first():
            new_user = models.User(
                username=username, 
                pin_hash=hash_pin(pin), # Mock hash function needed or use plain for local dev if implemented that way
                role=role
            )
            # Simple hash simulation if imported, else just store plain for this script
            # new_user.pin_hash = pin # Storing plain for dev environment simplicity/speed in this script
            db.add(new_user)
    db.commit()

    # 3. Orders (PVC & ALU)
    orders_data = [
        {"ref": "CMD-2024-001", "mat": "PVC", "w": 100, "h": 120},
        {"ref": "CMD-2024-002", "mat": "PVC", "w": 200, "h": 215},
        {"ref": "CMD-2024-003", "mat": "PVC", "w": 80, "h": 60},  # Small window
        {"ref": "CMD-2024-004", "mat": "ALU", "w": 150, "h": 150},
        {"ref": "CMD-2024-005", "mat": "PVC", "w": 120, "h": 100},
        {"ref": "CMD-2024-006", "mat": "PVC", "w": 90, "h": 210}, # Door
        {"ref": "CMD-2024-007", "mat": "PVC", "w": 100, "h": 100},
    ]

    db_orders = {}
    for o in orders_data:
        existing = db.query(models.Order).filter(models.Order.reference == o["ref"]).first()
        if not existing:
            new_order = models.Order(reference=o["ref"], material=o["mat"], width=o["w"], height=o["h"])
            db.add(new_order)
            db.commit()
            db.refresh(new_order)
            db_orders[o["ref"]] = new_order
        else:
            db_orders[o["ref"]] = existing

    # 4. Production Scenario (Planning & Logs)

    # A. Completed Orders (Done at Debit, waiting at Soudure)
    # CMD-001: DONE at DEBIT -> PENDING at SOUDURE
    create_task(db, db_orders["CMD-2024-001"], models.StationName.PVC_DEBIT, models.PlanningStatus.DONE)
    create_task(db, db_orders["CMD-2024-001"], models.StationName.PVC_SOUDURE, models.PlanningStatus.PENDING, priority=10)

    # B. In Progress Orders
    # CMD-002: IN_PROGRESS at DEBIT
    create_task(db, db_orders["CMD-2024-002"], models.StationName.PVC_DEBIT, models.PlanningStatus.IN_PROGRESS, priority=8)
    # Simulate active log
    create_log(db, db_orders["CMD-2024-002"], models.StationName.PVC_DEBIT, start_offset_minutes=15)

    # C. Paused Order (Problem?)
    # CMD-003: PAUSED at DEBIT
    create_task(db, db_orders["CMD-2024-003"], models.StationName.PVC_DEBIT, models.PlanningStatus.PAUSED, priority=5)

    # D. Defect Order (Alert!)
    # CMD-004 (ALU): DEFECT at DEBIT
    create_task(db, db_orders["CMD-2024-004"], models.StationName.ALU_DEBIT, models.PlanningStatus.DEFECT, priority=9)
    
    # E. Pending Orders (Backlog)
    create_task(db, db_orders["CMD-2024-005"], models.StationName.PVC_DEBIT, models.PlanningStatus.PENDING, priority=4)
    create_task(db, db_orders["CMD-2024-006"], models.StationName.PVC_DEBIT, models.PlanningStatus.PENDING, priority=3)
    create_task(db, db_orders["CMD-2024-007"], models.StationName.PVC_DEBIT, models.PlanningStatus.PENDING, priority=2)

    db.commit()
    print("--- Scenario Loaded Successfully ---")
    print("Users: admin(1234), op_debit(1111), op_soudure(2222)")
    print("Orders: 001 (Soudure Pending), 002 (Debit In Progress), 003 (Debit Paused), 004 (Defect)")
    db.close()

def create_task(db, order, station, status, priority=0):
    existing = db.query(models.Planning).filter(
        models.Planning.order_id == order.id,
        models.Planning.station == station
    ).first()
    
    if not existing:
        task = models.Planning(
            order_id=order.id,
            station=station,
            status=status,
            priority=priority,
            created_at=datetime.utcnow()
        )
        db.add(task)
    else:
        existing.status = status
        existing.priority = priority

def create_log(db, order, station, start_offset_minutes=0):
    start_time = datetime.utcnow() - timedelta(minutes=start_offset_minutes)
    log = models.ProductionLog(
        order_id=order.id,
        station=station,
        material=order.material,
        start_time=start_time,
        end_time=None 
    )
    db.add(log)

# Mock hash (reuse common/utils if available, simplified here)
def hash_pin(pin): 
    return pwd_context.hash(pin)

if __name__ == "__main__":
    seed_scenario()
