from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
import os
import secrets
from ..database import get_db
from .. import models, schemas
from ..core import security
from ..core.events import _send_smtp_email

router = APIRouter(
    prefix="/v2/config",
    tags=["config"],
    dependencies=[Depends(security.get_current_user)],
)
PIN_ROLES = {"OPERATOR", "DEBIT_OPERATOR", "QUALITY_CONTROLLER", "WORKSHOP_LEAD", "MAGASINIER"}
ACCESS_MODES = {"PIN", "EMAIL", "HYBRID"}

def _load_secondary_roles(db: Session, primary_role: str, additional_roles: List[str]):
    role_names = []
    for role_name in additional_roles or []:
        normalized = (role_name or "").strip().upper()
        if normalized and normalized != primary_role and normalized not in role_names:
            role_names.append(normalized)
    if not role_names:
        return []
    roles = db.query(models.Role).filter(models.Role.name.in_(role_names)).all()
    found = {role.name for role in roles}
    missing = [role_name for role_name in role_names if role_name not in found]
    if missing:
        raise HTTPException(400, f"Rôle(s) complémentaire(s) inconnu(s): {', '.join(missing)}")
    return roles

def _temporary_secret(access_mode: str, role_name: str) -> str:
    if access_mode == "PIN" or role_name in PIN_ROLES:
        return f"{secrets.randbelow(10000):04d}"
    return secrets.token_urlsafe(12)

def _validate_user_secret(secret: str, role_name: str, access_mode: str) -> None:
    if access_mode == "PIN" or role_name in PIN_ROLES:
        if not secret.isdigit() or len(secret) != 4:
            raise HTTPException(400, "Le code PIN atelier doit être composé de 4 chiffres")
    elif len(secret) < 8:
        raise HTTPException(400, "Le mot de passe temporaire doit faire au moins 8 caractères")

def _invite_link(token: str) -> str:
    base_url = (os.environ.get("FRONTEND_BASE_URL") or os.environ.get("APP_BASE_URL") or "").strip().rstrip("/")
    if not base_url:
        return f"INVITE-TOKEN:{token}"
    return f"{base_url}/login?invite={token}"

def _send_user_invitation_email(recipient: str, display_name: str, username: str, role_name: str, invite_link: str) -> bool:
    subject = "Invitation MMG - Accès plateforme"
    text_body = (
        f"Bonjour {display_name},\n\n"
        "Votre accès MMG est prêt.\n"
        f"Identifiant : {username}\n"
        f"Profil : {role_name}\n\n"
        f"Lien d'invitation : {invite_link}\n\n"
        "Si vous utilisez un terminal atelier, votre responsable peut aussi vous remettre un PIN temporaire.\n"
    )
    html_body = (
        f"<p>Bonjour <strong>{display_name}</strong>,</p>"
        "<p>Votre accès MMG est prêt.</p>"
        f"<p><strong>Identifiant :</strong> {username}<br><strong>Profil :</strong> {role_name}</p>"
        f"<p><a href=\"{invite_link}\">Ouvrir mon accès MMG</a></p>"
        "<p>Si vous utilisez un terminal atelier, votre responsable peut aussi vous remettre un PIN temporaire.</p>"
    )
    return _send_smtp_email(recipient, subject, text_body, html_body)

def _send_invitation_best_effort(recipient: str, display_name: str, username: str, role_name: str, invite_link: str) -> None:
    try:
        _send_user_invitation_email(recipient, display_name, username, role_name, invite_link)
    except Exception:
        # L'invitation ne doit jamais annuler la création d'accès. Le statut
        # reste PENDING côté UI pour permettre un renvoi manuel.
        pass

@router.get("/stations", response_model=List[schemas.Station])
def get_stations(db: Session = Depends(get_db)):
    return db.query(models.Station).order_by(models.Station.material, models.Station.order_index).all()

@router.post("/stations", response_model=schemas.Station)
def create_station(station: schemas.StationCreate, db: Session = Depends(get_db), role: str = Depends(security.require_roles("ADMIN", "MANAGER"))):
    # Check if code exists
    existing = db.query(models.Station).filter(models.Station.code == station.code).first()
    if existing:
        raise HTTPException(400, "Station code already exists")
    
    new_station = models.Station(**station.model_dump())
    db.add(new_station)
    db.commit()
    db.refresh(new_station)
    return new_station

@router.put("/stations/{station_id}", response_model=schemas.Station)
def update_station(station_id: int, station: schemas.StationBase, db: Session = Depends(get_db), role: str = Depends(security.require_roles("ADMIN", "MANAGER"))):
    db_station = db.query(models.Station).filter(models.Station.id == station_id).first()
    if not db_station:
        raise HTTPException(404, "Station not found")
    
    for key, value in station.model_dump().items():
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

@router.post("/users", response_model=schemas.UserCreateResponse)
def create_user(
    user: schemas.UserCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    role: str = Depends(security.require_roles("ADMIN", "MANAGER")),
):
    existing = db.query(models.User).filter(models.User.username == user.username).first()
    if existing:
        raise HTTPException(400, "Username already exists")

    access_mode = (user.access_mode or "PIN").upper()
    if access_mode not in ACCESS_MODES:
        raise HTTPException(400, "Mode d'accès invalide. Utilisez PIN, EMAIL ou HYBRID.")
    if user.send_invite and not user.email:
        raise HTTPException(400, "Un email est requis pour envoyer une invitation.")
    primary_role = user.role.upper()

    temporary_secret = user.pin or _temporary_secret(access_mode, primary_role)
    _validate_user_secret(temporary_secret, primary_role, access_mode)
    invite_token = secrets.token_urlsafe(24) if user.send_invite or access_mode in {"EMAIL", "HYBRID"} else None
    invitation_link = _invite_link(invite_token) if invite_token else None
    hashed_pin = security.get_password_hash(temporary_secret)
    new_user = models.User(
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        phone=user.phone,
        job_title=user.job_title,
        team=user.team,
        access_mode=access_mode,
        invitation_status="PENDING" if user.send_invite else "ACTIVE",
        invite_token=invite_token,
        pin_must_change=True,
        pin_hash=hashed_pin,
        role=primary_role,
        is_active=True,
        weekly_hours=user.weekly_hours,
        work_schedule=user.work_schedule,
    )
    new_user.secondary_roles = _load_secondary_roles(db, primary_role, user.additional_roles)
    
    if user.station_codes:
        stations = db.query(models.Station).filter(models.Station.code.in_(user.station_codes)).all()
        new_user.stations = stations

    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    invitation_sent = False
    if user.send_invite and user.email and invitation_link:
        display_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username
        background_tasks.add_task(
            _send_invitation_best_effort,
            user.email,
            display_name,
            user.username,
            primary_role,
            invitation_link,
        )
        invitation_sent = True
    return {
        "user": new_user,
        "temporary_pin": temporary_secret,
        "invitation_sent": invitation_sent,
        "invitation_link": invitation_link,
        "message": "Utilisateur créé. Communiquez le PIN temporaire une seule fois." if not user.send_invite else "Utilisateur créé. Invitation email planifiée.",
    }

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
    if user_update.job_title is not None:
        db_user.job_title = user_update.job_title
    if user_update.team is not None:
        db_user.team = user_update.team
    if user_update.access_mode is not None:
        access_mode = user_update.access_mode.upper()
        if access_mode not in ACCESS_MODES:
            raise HTTPException(400, "Mode d'accès invalide. Utilisez PIN, EMAIL ou HYBRID.")
        db_user.access_mode = access_mode
    if user_update.role:
        db_user.role = user_update.role.upper()
        db_user.secondary_roles = [role for role in db_user.secondary_roles if role.name != db_user.role]
    if user_update.weekly_hours is not None:
        if not 0 < user_update.weekly_hours <= 60:
            raise HTTPException(400, "La durée hebdomadaire doit être comprise entre 0 et 60 heures.")
        db_user.weekly_hours = user_update.weekly_hours
    if user_update.work_schedule is not None:
        db_user.work_schedule = user_update.work_schedule
    if user_update.additional_roles is not None:
        db_user.secondary_roles = _load_secondary_roles(db, db_user.role, user_update.additional_roles)
    if user_update.pin:
        if db_user.role in PIN_ROLES or user_update.role in PIN_ROLES:
            if not user_update.pin.isdigit() or len(user_update.pin) != 4:
                raise HTTPException(400, "Le code PIN Opérateur doit être composé de 4 chiffres")
        else:
            if len(user_update.pin) < 4:
                raise HTTPException(400, "Le mot de passe doit faire au moins 4 caractères")
        db_user.pin_hash = security.get_password_hash(user_update.pin)
        db_user.pin_must_change = True
    
    if user_update.station_codes is not None:
        stations = db.query(models.Station).filter(models.Station.code.in_(user_update.station_codes)).all()
        db_user.stations = stations
    
    db.commit()
    db.refresh(db_user)
    return db_user

@router.post("/users/{user_id}/invite", response_model=schemas.UserCreateResponse)
def resend_user_invitation(
    user_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    role: str = Depends(security.require_roles("ADMIN", "MANAGER")),
):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(404, "User not found")
    if not db_user.email:
        raise HTTPException(400, "Impossible d'envoyer une invitation sans email.")

    db_user.invite_token = secrets.token_urlsafe(24)
    db_user.invitation_status = "PENDING"
    db_user.invited_at = None
    db.commit()
    db.refresh(db_user)
    invitation_link = _invite_link(db_user.invite_token)
    display_name = f"{db_user.first_name or ''} {db_user.last_name or ''}".strip() or db_user.username
    background_tasks.add_task(
        _send_invitation_best_effort,
        db_user.email,
        display_name,
        db_user.username,
        db_user.role,
        invitation_link,
    )
    return {
        "user": db_user,
        "temporary_pin": None,
        "invitation_sent": True,
        "invitation_link": invitation_link,
        "message": "Invitation email planifiée.",
    }

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
    new_config = models.AppConfig(**config.model_dump())
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
def update_role_permissions(role_id: int, permission_ids: List[int], db: Session = Depends(get_db), role_name: str = Depends(security.require_roles("ADMIN", "SUPER_ADMIN"))):
    db_role = db.query(models.Role).filter(models.Role.id == role_id).first()
    if not db_role:
        raise HTTPException(404, "Role not found")
        
    permissions = db.query(models.Permission).filter(models.Permission.id.in_(permission_ids)).all()
    db_role.permissions = permissions
    db.commit()
    return {"status": "success"}

@router.post("/roles", response_model=schemas.RoleSchema)
def create_role(role: schemas.RoleCreate, db: Session = Depends(get_db), role_name: str = Depends(security.require_roles("ADMIN", "SUPER_ADMIN"))):
    existing = db.query(models.Role).filter(models.Role.name == role.name.upper()).first()
    if existing:
        raise HTTPException(400, "Ce rôle existe déjà")
        
    db_role = models.Role(name=role.name.upper(), description=role.description)
    db.add(db_role)
    db.commit()
    db.refresh(db_role)
    return db_role

@router.delete("/roles/{role_id}")
def delete_role(role_id: int, db: Session = Depends(get_db), role_name: str = Depends(security.require_roles("ADMIN", "SUPER_ADMIN"))):
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
    
    new_rule = models.BusinessRule(**req.model_dump())
    db.add(new_rule)
    db.commit()
    db.refresh(new_rule)
    return new_rule
