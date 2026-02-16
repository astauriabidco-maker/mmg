from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from .. import models, schemas
from ..core import security

router = APIRouter(prefix="/v2/config", tags=["config"])

@router.get("/stations", response_model=List[schemas.Station])
def get_stations(db: Session = Depends(get_db)):
    return db.query(models.Station).order_by(models.Station.material, models.Station.order_index).all()

@router.post("/stations", response_model=schemas.Station)
def create_station(station: schemas.StationCreate, db: Session = Depends(get_db)):
    # Check if code exists
    existing = db.query(models.Station).filter(models.Station.code == station.code).first()
    if existing:
        raise HTTPException(400, "Station code already exists")
    
    new_station = models.Station(**station.dict())
    db.add(new_station)
    db.commit()
    db.refresh(new_station)
    return new_station

@router.put("/stations/{station_id}", response_model=schemas.Station)
def update_station(station_id: int, station: schemas.StationBase, db: Session = Depends(get_db)):
    db_station = db.query(models.Station).filter(models.Station.id == station_id).first()
    if not db_station:
        raise HTTPException(404, "Station not found")
    
    for key, value in station.dict().items():
        setattr(db_station, key, value)
    
    db.commit()
    db.refresh(db_station)
    return db_station

@router.delete("/stations/{station_id}")
def delete_station(station_id: int, db: Session = Depends(get_db)):
    db_station = db.query(models.Station).filter(models.Station.id == station_id).first()
    if not db_station:
        raise HTTPException(404, "Station not found")
    
    db.delete(db_station)
    db.commit()
    return {"status": "deleted"}

@router.post("/stations/reorder")
def reorder_stations(order_map: dict, db: Session = Depends(get_db)):
    """
    Expects { station_id: new_index, ... }
    """
    for s_id, idx in order_map.items():
        db.query(models.Station).filter(models.Station.id == int(s_id)).update({"order_index": idx})
    db.commit()
    return {"status": "reordered"}

# --- USER / OPERATOR MANAGEMENT ---

@router.get("/users", response_model=List[schemas.User])
def get_users(db: Session = Depends(get_db)):
    return db.query(models.User).filter(models.User.role == models.UserRole.OPERATOR).all()

@router.post("/users", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.username == user.username).first()
    if existing:
        raise HTTPException(400, "Username already exists")
    
    # PIN must be 4 digits
    if not user.pin.isdigit() or len(user.pin) != 4:
        raise HTTPException(400, "PIN must be 4 digits")

    hashed_pin = security.get_password_hash(user.pin)
    new_user = models.User(
        username=user.username,
        pin_hash=hashed_pin,
        role=user.role,
        is_active=True
    )
    
    if user.station_codes:
        stations = db.query(models.Station).filter(models.Station.code.in_(user.station_codes)).all()
        new_user.stations = stations

    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.put("/users/{user_id}", response_model=schemas.User)
def update_user(user_id: int, user_update: schemas.UserUpdate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(404, "User not found")
    
    if user_update.username:
        db_user.username = user_update.username
    if user_update.role:
        db_user.role = user_update.role
    if user_update.pin:
        if not user_update.pin.isdigit() or len(user_update.pin) != 4:
            raise HTTPException(400, "PIN must be 4 digits")
        db_user.pin_hash = security.get_password_hash(user_update.pin)
    
    if user_update.station_codes is not None:
        stations = db.query(models.Station).filter(models.Station.code.in_(user_update.station_codes)).all()
        db_user.stations = stations
    
    db.commit()
    db.refresh(db_user)
    return db_user

@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(404, "User not found")
    
    db.delete(db_user)
    db.commit()
    return {"status": "deleted"}

# Removed @router.put("/users/{user_id}/station") as it's merged into update_user
