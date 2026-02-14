from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from .. import models, schemas

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
