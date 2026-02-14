from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models
from .. import printer
import os

router = APIRouter(prefix="/v2/printer", tags=["printer"])

@router.post("/reprint/{order_ref}")
def reprint_label(order_ref: str, db: Session = Depends(get_db)):
    # 1. Find Order
    order = db.query(models.Order).filter(models.Order.reference == order_ref).first()
    if not order:
        raise HTTPException(404, "Order not found")
        
    # 2. Re-generate PDF (or find existing)
    # For V1 simplicity, we assume PDF exists at known path
    # e.g. ./generated_qr/CMD-XXX.pdf
    
    file_path = f"generated_qr/{order_ref}.pdf"
    
    if not os.path.exists(file_path):
        # Fallback: Generate it on the fly? 
        # For now, 404
        raise HTTPException(404, "Label file not found on server")
        
    # 3. Send to Printer
    try:
        printer.print_label(file_path)
        return {"status": "sent_to_printer", "file": file_path}
    except Exception as e:
        raise HTTPException(500, f"Print failed: {str(e)}")
