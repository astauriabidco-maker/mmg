from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from backend.database import get_db
from backend import models
from backend.core import security

router = APIRouter(
    prefix="/v2/suppliers",
    tags=["V2 Suppliers"],
    dependencies=[Depends(security.get_current_user)],
)

class SupplierBase(BaseModel):
    name: str
    contact_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    tax_id: Optional[str] = None
    website: Optional[str] = None
    payment_terms: Optional[str] = None
    lead_time_days: Optional[int] = None
    preferred_contact_method: Optional[str] = None
    notes: Optional[str] = None

class SupplierCreate(SupplierBase):
    pass

@router.get("/")
def get_suppliers(db: Session = Depends(get_db)):
    return db.query(models.Supplier).filter(models.Supplier.is_active == True).order_by(models.Supplier.name).all()

@router.post("/")
def create_supplier(supplier: SupplierCreate, db: Session = Depends(get_db)):
    db_sup = db.query(models.Supplier).filter(models.Supplier.name == supplier.name).first()
    if db_sup:
        raise HTTPException(status_code=400, detail="Supplier already exists")
    
    new_sup = models.Supplier(**supplier.model_dump())
    db.add(new_sup)
    db.commit()
    db.refresh(new_sup)
    return new_sup

@router.put("/{supplier_id}")
def update_supplier(supplier_id: int, supplier: SupplierCreate, db: Session = Depends(get_db)):
    db_sup = db.query(models.Supplier).filter(models.Supplier.id == supplier_id).first()
    if not db_sup:
        raise HTTPException(status_code=404, detail="Supplier not found")
        
    for key, value in supplier.model_dump().items():
        setattr(db_sup, key, value)
        
    db.commit()
    db.refresh(db_sup)
    return db_sup

@router.delete("/{supplier_id}")
def delete_supplier(supplier_id: int, db: Session = Depends(get_db)):
    db_sup = db.query(models.Supplier).filter(models.Supplier.id == supplier_id).first()
    if not db_sup:
        raise HTTPException(status_code=404, detail="Supplier not found")
        
    db_sup.is_active = False # Soft delete
    db.commit()
    return {"status": "deleted"}
