from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from . import models, database
from .routers import web, api, v2_planning, v2_analytics, v2_printer, v2_ingest, v2_config, v2_mmg
from .core.websocket import manager
from fastapi import WebSocket, WebSocketDisconnect

from fastapi.middleware.cors import CORSMiddleware

# Initialize DB
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Atelier Menuiserie V1 Pro")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For production, specify ["http://localhost:5173"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static Config (CSS, JS)
app.mount("/static", StaticFiles(directory="backend/static"), name="static")

# Include Routers
app.include_router(web.router)
app.include_router(api.router)
app.include_router(v2_planning.router)
app.include_router(v2_analytics.router)
app.include_router(v2_printer.router)
app.include_router(v2_ingest.router)
app.include_router(v2_config.router)
app.include_router(v2_mmg.router)

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
    new_order = models.Order(**order.dict())
    db.add(new_order)
    db.commit()
    db.refresh(new_order)
    return new_order

@app.get("/dashboard/summary")
def api_dashboard():
    return {"status": "moved_to_web_ui"}

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
            "role": user.role.value, 
            "stations": [s.code for s in user.stations]
        }
    )
    return {
        "access_token": access_token, 
        "token_type": "bearer", 
        "role": user.role.value, 
        "stations": [s.code for s in user.stations]
    }
