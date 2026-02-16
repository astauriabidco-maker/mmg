from sqlalchemy import Column, Integer, String, Enum as SAEnum, DateTime, ForeignKey, Float, Boolean
from sqlalchemy.orm import relationship
from .database import Base
import enum
from datetime import datetime

class MaterialType(str, enum.Enum):
    PVC = "PVC"
    ALU = "ALU"
    UNKNOWN = "UNKNOWN"

class StationName(str, enum.Enum):
    # PVC Stations
    PVC_DEBIT = "PVC_DEBIT"
    PVC_SOUDURE = "PVC_SOUDURE"
    PVC_ASSEMBLAGE = "PVC_ASSEMBLAGE"
    PVC_VITRAGE = "PVC_VITRAGE"
    PVC_CONTROLE = "PVC_CONTROLE"
    
    # ALU Stations
    ALU_DEBIT = "ALU_DEBIT"
    ALU_USINAGE = "ALU_USINAGE"
    ALU_ASSEMBLAGE = "ALU_ASSEMBLAGE"
    ALU_VITRAGE = "ALU_VITRAGE"
    ALU_CONTROLE = "ALU_CONTROLE"

class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"

class PlanningStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    DONE = "DONE"
    DEFECT = "DEFECT"
    ISSUE = "ISSUE"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    pin_hash = Column(String) # Hashed 4-digit PIN
    role = Column(SAEnum(UserRole), default=UserRole.OPERATOR)
    is_active = Column(Boolean, default=True)
    
    # Many-to-many relationship with Stations
    stations = relationship("Station", secondary="user_stations")

class UserStation(Base):
    __tablename__ = "user_stations"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    station_id = Column(Integer, ForeignKey("stations.id"), primary_key=True)

class Planning(Base):
    __tablename__ = "planning"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    station = Column(String) # Changed from Enum to String
    priority = Column(Integer, default=0) # Higher = More urgent
    status = Column(SAEnum(PlanningStatus), default=PlanningStatus.PENDING)
    issue_notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order")

    @property
    def order_reference(self):
        return self.order.reference if self.order else f"ORD-{self.order_id}"

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True) # Ex: CMD-XXXX
    width = Column(Float)
    height = Column(Float)
    material = Column(SAEnum(MaterialType))
    
    # New Fields
    client_name = Column(String, nullable=True)
    color = Column(String, nullable=True)
    quantity = Column(Integer, default=1)
    system_type = Column(String, nullable=True)
    
    logs = relationship("ProductionLog", back_populates="order")

class ProductionLog(Base):
    __tablename__ = "production_logs"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    station = Column(String) # Changed from Enum to String
    material = Column(String) # PVC or ALU
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    order = relationship("Order", back_populates="logs")

class Station(Base):
    __tablename__ = "stations"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True) # ex: PVC_DEBIT
    display_name = Column(String) # ex: Débit PVC
    material = Column(SAEnum(MaterialType)) # PVC or ALU
    order_index = Column(Integer, default=0) # Sequence order

class MMGStatus(str, enum.Enum):
    SENT = "SENT"
    IN_STUDY = "IN_STUDY"
    VALIDATED = "VALIDATED"
    IN_PRODUCTION = "IN_PRODUCTION"

class MMG(Base):
    __tablename__ = "mmg_dossiers"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True) # MMG-2026-XXXXX
    client_name = Column(String)
    client_contact = Column(String)
    client_address = Column(String) # Billing address
    site_address = Column(String, nullable=True) # Adresse du chantier
    client_email = Column(String)
    client_type = Column(String, default="PARTICULIER") # PRO / PARTICULIER
    
    width = Column(Float)
    height = Column(Float)
    passage_height = Column(Float)
    
    sill_height = Column(Float, nullable=True) # Hsoubassement
    transom_height = Column(Float, nullable=True) # Himposte
    shutter_type = Column(String, nullable=True) # gauche/droite/centre
    
    opening_type = Column(String) # tirant/poussant
    opening_side = Column(String) # gauche/droite
    sash_count = Column(Integer) # 1/2/3
    view_type = Column(String, default="interior") # interior/exterior
    
    # Professional & Quoting Fields
    material = Column(String, nullable=True) # ALU, PVC, etc.
    product_series = Column(String, nullable=True) # Standard, Premium, etc.
    color_ral = Column(String, nullable=True) # Ex: RAL 7016
    is_bicolor = Column(Boolean, default=False)
    texture = Column(String, nullable=True) # Sablé, Grainé
    glazing_type = Column(String, nullable=True) # Ex: 4/16/4
    installation_type = Column(String, nullable=True) # Neuf, Reno
    doublage_thickness = Column(String, nullable=True) # For Neuf: 70, 100, etc.
    keep_existing_frame = Column(Boolean, default=False) # For Reno
    
    hardware_type = Column(String, nullable=True) # Standard, Security
    is_pmr_compliant = Column(Boolean, default=False)
    
    # Logistics
    floor_number = Column(Integer, default=0)
    access_difficulty = Column(String, nullable=True) # None, Crane, etc.
    environment = Column(String, default="Standard") # Standard, Coastal, Urban High-Rise
    
    photos = Column(String) # Comma separated filenames or JSON list
    signature = Column(String) # Path to signature image
    
    # Sales info
    quote_sent_at = Column(DateTime, nullable=True)
    
    status = Column(SAEnum(MMGStatus), default=MMGStatus.SENT)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Link to Order (once validated and imported)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    order = relationship("Order")
