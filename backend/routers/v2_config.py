from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from .. import models, schemas
from ..core import security

router = APIRouter(
    prefix="/v2/config",
    tags=["config"],
    dependencies=[Depends(security.get_current_user)],
)

@router.get("/stations", response_model=List[schemas.Station])
def get_stations(db: Session = Depends(get_db)):
    return db.query(models.Station).order_by(models.Station.material, models.Station.order_index).all()

@router.post("/stations", response_model=schemas.Station)
def create_station(station: schemas.StationCreate, db: Session = Depends(get_db), role: str = Depends(security.require_roles("ADMIN", "MANAGER"))):
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
def update_station(station_id: int, station: schemas.StationBase, db: Session = Depends(get_db), role: str = Depends(security.require_roles("ADMIN", "MANAGER"))):
    db_station = db.query(models.Station).filter(models.Station.id == station_id).first()
    if not db_station:
        raise HTTPException(404, "Station not found")
    
    for key, value in station.dict().items():
        setattr(db_station, key, value)
    
    db.commit()
    db.refresh(db_station)
    return db_station

@router.delete("/stations/{station_id}")
def delete_station(station_id: int, db: Session = Depends(get_db), role: str = Depends(security.require_roles("ADMIN", "MANAGER"))):
    db_station = db.query(models.Station).filter(models.Station.id == station_id).first()
    if not db_station:
        raise HTTPException(404, "Station not found")
    
    db.delete(db_station)
    db.commit()
    return {"status": "deleted"}

@router.post("/stations/reorder")
def reorder_stations(order_map: dict, db: Session = Depends(get_db), role: str = Depends(security.require_roles("ADMIN", "MANAGER"))):
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
    return db.query(models.User).all()

@router.post("/users", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db), role: str = Depends(security.require_roles("ADMIN", "MANAGER"))):
    existing = db.query(models.User).filter(models.User.username == user.username).first()
    if existing:
        raise HTTPException(400, "Username already exists")
    
    # PIN/Password validation
    if user.role == "OPERATOR":
        if not user.pin.isdigit() or len(user.pin) != 4:
            raise HTTPException(400, "Le code PIN Opérateur doit être composé de 4 chiffres")
    else:
        if len(user.pin) < 4:
            raise HTTPException(400, "Le mot de passe doit faire au moins 4 caractères")

    hashed_pin = security.get_password_hash(user.pin)
    new_user = models.User(
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        phone=user.phone,
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
def update_user(user_id: int, user_update: schemas.UserUpdate, db: Session = Depends(get_db), role: str = Depends(security.require_roles("ADMIN", "MANAGER"))):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(404, "User not found")
    
    if user_update.username:
        db_user.username = user_update.username
    if user_update.first_name is not None:
        db_user.first_name = user_update.first_name
    if user_update.last_name is not None:
        db_user.last_name = user_update.last_name
    if user_update.email is not None:
        db_user.email = user_update.email
    if user_update.phone is not None:
        db_user.phone = user_update.phone
    if user_update.role:
        db_user.role = user_update.role
    if user_update.pin:
        if db_user.role == "OPERATOR" or user_update.role == "OPERATOR":
            if not user_update.pin.isdigit() or len(user_update.pin) != 4:
                raise HTTPException(400, "Le code PIN Opérateur doit être composé de 4 chiffres")
        else:
            if len(user_update.pin) < 4:
                raise HTTPException(400, "Le mot de passe doit faire au moins 4 caractères")
        db_user.pin_hash = security.get_password_hash(user_update.pin)
    
    if user_update.station_codes is not None:
        stations = db.query(models.Station).filter(models.Station.code.in_(user_update.station_codes)).all()
        db_user.stations = stations
    
    db.commit()
    db.refresh(db_user)
    return db_user

@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), role: str = Depends(security.require_roles("ADMIN", "MANAGER"))):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(404, "User not found")
    
    db.delete(db_user)
    db.commit()
    return {"status": "deleted"}

# Removed @router.put("/users/{user_id}/station") as it's merged into update_user

# --- APP CONFIGS (REFERENTIELS) ---

@router.get("/app_configs", response_model=List[schemas.AppConfigResponse])
def get_app_configs(db: Session = Depends(get_db)):
    return db.query(models.AppConfig).all()

@router.post("/app_configs", response_model=schemas.AppConfigResponse)
def create_app_config(config: schemas.AppConfigCreate, db: Session = Depends(get_db), role: str = Depends(security.require_roles("ADMIN", "MANAGER"))):
    new_config = models.AppConfig(**config.dict())
    db.add(new_config)
    db.commit()
    db.refresh(new_config)
    return new_config

@router.delete("/app_configs/{config_id}")
def delete_app_config(config_id: int, db: Session = Depends(get_db), role: str = Depends(security.require_roles("ADMIN", "MANAGER"))):
    db_config = db.query(models.AppConfig).filter(models.AppConfig.id == config_id).first()
    if db_config:
        db.delete(db_config)
        db.commit()
    return {"status": "deleted"}

# --- RBAC (ROLES & PERMISSIONS) ---

@router.get("/roles", response_model=List[schemas.RoleSchema])
def get_roles(db: Session = Depends(get_db)):
    from sqlalchemy.orm import joinedload
    return db.query(models.Role).options(joinedload(models.Role.permissions)).all()

@router.get("/permissions", response_model=List[schemas.PermissionSchema])
def get_permissions(db: Session = Depends(get_db)):
    return db.query(models.Permission).all()

@router.post("/roles/{role_id}/permissions")
def update_role_permissions(role_id: int, permission_ids: List[int], db: Session = Depends(get_db), role_name: str = Depends(security.require_roles("ADMIN"))):
    db_role = db.query(models.Role).filter(models.Role.id == role_id).first()
    if not db_role:
        raise HTTPException(404, "Role not found")
        
    permissions = db.query(models.Permission).filter(models.Permission.id.in_(permission_ids)).all()
    db_role.permissions = permissions
    db.commit()
    return {"status": "success"}

@router.post("/roles", response_model=schemas.RoleSchema)
def create_role(role: schemas.RoleCreate, db: Session = Depends(get_db), role_name: str = Depends(security.require_roles("ADMIN"))):
    existing = db.query(models.Role).filter(models.Role.name == role.name.upper()).first()
    if existing:
        raise HTTPException(400, "Ce rôle existe déjà")
        
    db_role = models.Role(name=role.name.upper(), description=role.description)
    db.add(db_role)
    db.commit()
    db.refresh(db_role)
    return db_role

@router.delete("/roles/{role_id}")
def delete_role(role_id: int, db: Session = Depends(get_db), role_name: str = Depends(security.require_roles("ADMIN"))):
    db_role = db.query(models.Role).filter(models.Role.id == role_id).first()
    if not db_role:
        raise HTTPException(404, "Role not found")
        
    # Prevent deleting ADMIN role
    if db_role.name == "ADMIN":
        raise HTTPException(400, "Impossible de supprimer le rôle Administrateur Système")
        
    db.delete(db_role)
    db.commit()
    return {"status": "deleted"}

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

@router.post("/test-smtp")
def test_smtp_configuration(req: schemas.SMTPTestRequest, role: str = Depends(security.require_roles("ADMIN", "MANAGER"))):
    try:
        msg = MIMEMultipart()
        msg['From'] = req.username
        msg['To'] = req.recipient
        msg['Subject'] = "MMG ERP - Test de Configuration SMTP"
        
        body = "Bonjour,\n\nCeci est un email de test envoyé depuis votre plateforme MMG ERP.\nSi vous recevez cet email, cela signifie que votre configuration SMTP est correcte.\n\nCordialement,\nL'équipe Technique MMG"
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(req.host, req.port)
        server.starttls()
        server.login(req.username, req.password)
        server.send_message(msg)
        server.quit()
        
        return {"status": "success", "message": "Email de test envoyé avec succès"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur SMTP: {str(e)}")

# --- BUSINESS RULES ---

@router.get("/rules", response_model=List[schemas.BusinessRuleSchema])
def get_business_rules(db: Session = Depends(get_db)):
    return db.query(models.BusinessRule).all()

@router.put("/rules/{rule_key}", response_model=schemas.BusinessRuleSchema)
def update_business_rule(rule_key: str, req: schemas.BusinessRuleUpdate, db: Session = Depends(get_db), role: str = Depends(security.require_roles("ADMIN", "MANAGER"))):
    rule = db.query(models.BusinessRule).filter(models.BusinessRule.rule_key == rule_key).first()
    if not rule:
        raise HTTPException(404, "Règle métier introuvable")
    rule.value = req.value
    db.commit()
    db.refresh(rule)
    return rule

@router.post("/rules", response_model=schemas.BusinessRuleSchema)
def create_business_rule(req: schemas.BusinessRuleCreate, db: Session = Depends(get_db), role: str = Depends(security.require_roles("ADMIN", "MANAGER"))):
    existing = db.query(models.BusinessRule).filter(models.BusinessRule.rule_key == req.rule_key).first()
    if existing:
        raise HTTPException(400, "Une règle avec cette clé existe déjà")
    
    new_rule = models.BusinessRule(**req.dict())
    db.add(new_rule)
    db.commit()
    db.refresh(new_rule)
    return new_rule
