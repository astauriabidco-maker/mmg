from backend.database import engine, SessionLocal
from backend.routers.v2_stock import delete_location

session = SessionLocal()
try:
    print(delete_location(5, session, "SUPER_ADMIN"))
except Exception as e:
    import traceback
    traceback.print_exc()
