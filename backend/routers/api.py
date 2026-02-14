from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import database, schemas
from ..services.production import ProductionService

router = APIRouter(prefix="/production", tags=["api"])

# Legacy API, using database.get_db directly

@router.post("/start", response_model=schemas.ProductionLog)
def api_start(action: schemas.ProductionStart, db: Session = Depends(database.get_db)):
    # Assuming logic infers material from Order if not provided in schema, 
    # but Service needs material. Order must exist or be fetched.
    # Legacy API didn't ask for material in payload usually, it was inferred.
    # Service expects material to create order if missing.
    # We fetch order first to get material if exists.
    
    # Logic adapter:
    existing_order = ProductionService.get_order(db, action.order_reference)
    material = existing_order.material if existing_order else "PVC" # Default if API calls without creating order
    
    log = ProductionService.start_production(db, action.order_reference, action.station, material)
    if not log:
        raise HTTPException(status_code=400, detail="Active or Error")
    return log

@router.post("/stop", response_model=schemas.ProductionLog)
def api_stop(action: schemas.ProductionStop, db: Session = Depends(database.get_db)):
    log = ProductionService.stop_production(db, action.order_reference, action.station)
    if not log:
        raise HTTPException(status_code=400, detail="Error stopping")
    return log
