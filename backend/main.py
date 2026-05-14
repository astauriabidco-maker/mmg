from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import os
from . import models, database
from .routers import api, v2_planning, v2_analytics, v2_printer, v2_ingest, v2_config, v2_mmg, v2_stock, v2_sales, v2_pos, v2_purchases, v2_suppliers, v2_pdf, v2_accounting, v2_logistics, v2_webhook
from .core.websocket import manager
from fastapi import WebSocket, WebSocketDisconnect

from fastapi.middleware.cors import CORSMiddleware

# Initialize DB
models.Base.metadata.create_all(bind=database.engine)
models.ensure_schema_compatibility(database.engine)
get_db = database.get_db
from .seed_stations import ensure_default_stations
ensure_default_stations()

app = FastAPI(title="Atelier Menuiserie V1 Pro")

# Configure CORS
allowed_origins = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:5000,http://127.0.0.1:5000,http://localhost:5173,http://127.0.0.1:5173,http://localhost:7000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Uploads (Zero UI, API ONLY)
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Include Routers
app.include_router(api.router)
app.include_router(v2_planning.router)
app.include_router(v2_analytics.router)
app.include_router(v2_printer.router)
app.include_router(v2_ingest.router)
app.include_router(v2_config.router)
app.include_router(v2_mmg.router)
app.include_router(v2_stock.router)
app.include_router(v2_sales.router)
app.include_router(v2_pos.router)
app.include_router(v2_purchases.router)
app.include_router(v2_suppliers.router)
app.include_router(v2_pdf.router)
app.include_router(v2_accounting.router)
app.include_router(v2_logistics.router)
app.include_router(v2_webhook.router)
from .routers import v2_partners
app.include_router(v2_partners.router)

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: int):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo or handle logic
            await manager.broadcast(f"Client #{client_id} says: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Legacy Orders Endpoint for Tests (Optional, keeping for robustness)
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from . import schemas
@app.post("/orders/", response_model=schemas.Order)
def create_order(order: schemas.OrderCreate, db: Session = Depends(database.get_db)):
    db_order = db.query(models.Order).filter(models.Order.reference == order.reference).first()
    if db_order: raise HTTPException(400, "Exists")
    new_order = models.Order(**order.model_dump())
    db.add(new_order)
    db.commit()
    db.refresh(new_order)
    return new_order



# --- AUTH ---
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from .core import security

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@app.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not security.verify_password(form_data.password, user.pin_hash):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    access_token = security.create_access_token(
        data={
            "sub": user.username, 
            "role": user.role, 
            "stations": [s.code for s in user.stations]
        }
    )
    return {
        "access_token": access_token, 
        "token_type": "bearer", 
        "role": user.role, 
        "stations": [s.code for s in user.stations]
    }
