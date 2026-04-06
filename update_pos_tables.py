from backend.database import engine, Base
from backend.models import SaleOrder, SaleOrderLine, POSSession, POSOrder, POSOrderLine
Base.metadata.create_all(bind=engine)
print("POS and Sales tables created successfully!")
