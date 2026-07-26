from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager, suppress
import asyncio
import os
import time
import uuid
from . import models, database
from .routers import api, v2_planning, v2_schedule, v2_analytics, v2_printer, v2_ingest, v2_config, v2_mmg, v2_stock, v2_sales, v2_pos, v2_purchases, v2_suppliers, v2_pdf, v2_accounting, v2_logistics, v2_webhook
from .core.websocket import manager
from .core import security
from .core.logger import logger
from .core.time import utcnow
from fastapi import WebSocket, WebSocketDisconnect

from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

# NOTE schéma : Alembic est la source de vérité unique du schéma
# (`alembic upgrade head`). Aucune écriture base de données n'a lieu à
# l'import de ce module : tout ce qui touche la DB est dans le lifespan.

get_db = database.get_db


async def _planning_alert_worker():
    interval_seconds = max(
        15,
        int(os.environ.get("PLANNING_ALERT_INTERVAL_SECONDS", "60")),
    )
    from .services.planning_alerts import evaluate_operational_alerts

    while True:
        await asyncio.sleep(interval_seconds)
        db = database.SessionLocal()
        try:
            created = evaluate_operational_alerts(db)
            db.commit()
            if created:
                logger.info(
                    "planning_operational_alerts_created count=%s",
                    created,
                )
        except Exception:
            db.rollback()
            logger.exception("planning_operational_alert_evaluation_failed")
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialisation DB au démarrage (jamais à l'import du module).

    - create_all : simple filet de sécurité en développement (idempotent).
      Désactivé en production : sur Postgres, Alembic seul gère le schéma et
      un schéma non migré doit faire échouer le démarrage explicitement
      plutôt que d'être patché silencieusement.
    - seeds de données de référence (stations, rôles/permissions) :
      idempotents, exécutés dans tous les environnements.
    """
    if os.environ.get("APP_ENV", "development").lower() != "production":
        models.Base.metadata.create_all(bind=database.engine)
    from .seed_stations import ensure_default_stations
    ensure_default_stations()
    from .seed_permissions import seed_permissions
    seed_permissions()
    alert_worker = asyncio.create_task(_planning_alert_worker())
    try:
        yield
    finally:
        alert_worker.cancel()
        with suppress(asyncio.CancelledError):
            await alert_worker


app = FastAPI(title="Atelier Menuiserie V1 Pro", lifespan=lifespan)

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    logger.exception("request_id=%s unhandled_error path=%s", request_id, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )

# Configure CORS
default_cors_origins = (
    "http://localhost:5000,http://127.0.0.1:5000,"
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:7000"
)
raw_cors_origins = os.environ.get("CORS_ORIGINS", default_cors_origins)
app_env = os.environ.get("APP_ENV", "development").lower()
if app_env == "production" and raw_cors_origins == default_cors_origins:
    raise RuntimeError("CORS_ORIGINS must be explicitly set when APP_ENV=production")

allowed_origins = [
    origin.strip()
    for origin in raw_cors_origins.split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"] if app_env == "production" else ["*"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"] if app_env == "production" else ["*"],
    expose_headers=["Content-Disposition"],
)

# Mount Uploads (Zero UI, API ONLY)
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Include Routers
app.include_router(api.router)
app.include_router(v2_planning.router)
app.include_router(v2_schedule.router)
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
app.include_router(v2_pdf.public_router)
app.include_router(v2_accounting.router)
app.include_router(v2_logistics.router)
app.include_router(v2_webhook.router)
from .routers import v2_partners
app.include_router(v2_partners.router)

@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "service": "mmg-api"}

@app.get("/health/ready", tags=["health"])
def readiness_check(db: Session = Depends(database.get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}

@app.get("/invitations/{token}", tags=["auth"])
def get_user_invitation(token: str, db: Session = Depends(database.get_db)):
    user = (
        db.query(models.User)
        .filter(models.User.invite_token == token, models.User.is_active == True)  # noqa: E712
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Invitation introuvable ou expirée")
    display_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username
    return {
        "username": user.username,
        "display_name": display_name,
        "email": user.email,
        "role": user.role,
        "access_mode": user.access_mode,
        "invitation_status": user.invitation_status,
    }

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: int, token: str = ""):
    db = database.SessionLocal()
    try:
        security.authenticate_token(token, db)
    except HTTPException:
        await websocket.close(code=4401)
        return
    finally:
        db.close()
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo or handle logic
            await manager.broadcast(f"Client #{client_id} says: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

from . import schemas
@app.post("/orders/", response_model=schemas.Order)
def create_order(
    order: schemas.OrderCreate,
    db: Session = Depends(database.get_db),
    role: str = Depends(security.require_roles("ADMIN", "MANAGER")),
):
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
from .core.rate_limit import login_rate_limiter

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@app.post("/token")
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    # Rate limiting anti force brute (PIN à 4 chiffres) : compteur par
    # (IP client, username), 5 échecs -> blocage 10 min (429), remise à zéro
    # au succès. Voir backend/core/rate_limit.py pour la limite multi-instance.
    client_ip = request.client.host if request.client else "unknown"
    rate_key = (client_ip, form_data.username)
    blocked_for = login_rate_limiter.check_blocked(rate_key)
    if blocked_for > 0:
        raise HTTPException(
            status_code=429,
            detail=f"Trop de tentatives de connexion échouées. Réessayez dans {blocked_for // 60 + 1} minute(s).",
            headers={"Retry-After": str(blocked_for)},
        )

    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not security.verify_password(form_data.password, user.pin_hash):
        login_rate_limiter.record_failure(rate_key)
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    login_rate_limiter.reset(rate_key)
    user.last_login_at = utcnow()
    if user.invitation_status == "PENDING":
        user.invitation_status = "ACTIVE"
        user.invite_token = None
        user.pin_must_change = False
        db.commit()
    role_names = user.role_names
    permissions = security.get_permissions_for_roles(db, role_names)
    
    access_token = security.create_access_token(
        data={
            "sub": user.username, 
            "role": user.role, 
            "roles": role_names,
            "stations": [s.code for s in user.stations],
            "permissions": permissions,
        }
    )
    return {
        "access_token": access_token, 
        "token_type": "bearer", 
        "role": user.role, 
        "roles": role_names,
        "stations": [s.code for s in user.stations],
        "permissions": permissions,
    }
