from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from .models import MaterialType, StationName, UserRole, PlanningStatus

# --- AUTH & USERS ---

class UserBase(BaseModel):
    username: str
    role: UserRole = UserRole.OPERATOR
    station: Optional[str] = None # Support dynamic station codes

class UserCreate(UserBase):
    pin: str # 4 digits

class User(UserBase):
    id: int
    is_active: bool
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# --- PLANNING ---

class PlanningBase(BaseModel):
    station: str # Changed from StationName enum to str
    priority: int = 0
    status: PlanningStatus = PlanningStatus.PENDING

class PlanningCreate(PlanningBase):
    order_reference: str

class Planning(PlanningBase):
    id: int
    order_id: int
    order_reference: Optional[str] = None
    order: Optional['Order'] = None
    created_at: datetime
    class Config:
        from_attributes = True

# --- LOGS ---

class ProductionLogBase(BaseModel):
    station: str # Changed from StationName enum to str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[int] = None

class ProductionLog(ProductionLogBase):
    id: int
    order_id: int

    class Config:
        from_attributes = True

# --- ACTIONS ---

class ProductionStart(BaseModel):
    order_reference: str
    station: str

class ProductionStop(BaseModel):
    order_reference: str
    station: str

# --- ORDERS ---

class OrderBase(BaseModel):
    reference: str
    width: float
    height: float
    material: MaterialType
    client_name: Optional[str] = None
    color: Optional[str] = None
    quantity: int = 1
    system_type: Optional[str] = None

class OrderCreate(OrderBase):
    pass

class Order(OrderBase):
    id: int
    logs: List[ProductionLog] = []

    class Config:
        from_attributes = True

# --- STATIONS ---

class StationBase(BaseModel):
    code: str
    display_name: str
    material: MaterialType
    order_index: int = 0

class StationCreate(StationBase):
    pass

class Station(StationBase):
    id: int
    class Config:
        from_attributes = True
