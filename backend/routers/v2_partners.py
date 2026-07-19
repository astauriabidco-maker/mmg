from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from .. import models, schemas
from ..core import security

router = APIRouter(
    prefix="/v2/partners",
    tags=["partners"],
    dependencies=[Depends(security.get_current_user)],
)

# --- CLIENTS ---
@router.get("/clients", response_model=List[schemas.ClientResponse])
def get_clients(db: Session = Depends(get_db)):
    return db.query(models.Client).all()

@router.post("/clients", response_model=schemas.ClientResponse)
def create_client(client: schemas.ClientCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Client).filter(models.Client.name == client.name).first()
    if existing:
        raise HTTPException(400, "Client name already exists")
    db_client = models.Client(**client.model_dump())
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    return db_client

@router.put("/clients/{client_id}", response_model=schemas.ClientResponse)
def update_client(client_id: int, client: schemas.ClientCreate, db: Session = Depends(get_db)):
    db_client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not db_client:
        raise HTTPException(404, "Client not found")
    for k, v in client.model_dump().items():
        setattr(db_client, k, v)
    db.commit()
    db.refresh(db_client)
    return db_client

@router.delete("/clients/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db)):
    db_client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not db_client:
        raise HTTPException(404, "Client not found")
    db.delete(db_client)
    db.commit()
    return {"status": "deleted"}

# NOTE: le CRUD fournisseurs est unifié sur /v2/suppliers (routers/v2_suppliers.py).

