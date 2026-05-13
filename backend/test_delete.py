import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import engine, SessionLocal
from routers.v2_stock import delete_location

session = SessionLocal()
try:
    print(delete_location(7, session, "SUPER_ADMIN"))
except Exception as e:
    print("EXCEPTION:", repr(e))
