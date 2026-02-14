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

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    pin_hash = Column(String) # Hashed 4-digit PIN
    role = Column(SAEnum(UserRole), default=UserRole.OPERATOR)
    station = Column(String, nullable=True) # Changed from Enum to String for flexibility
    is_active = Column(Boolean, default=True)

class Planning(Base):
    __tablename__ = "planning"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    station = Column(String) # Changed from Enum to String
    priority = Column(Integer, default=0) # Higher = More urgent
    status = Column(SAEnum(PlanningStatus), default=PlanningStatus.PENDING)
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
