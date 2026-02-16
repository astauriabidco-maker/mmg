from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from .models import MaterialType, StationName, UserRole, PlanningStatus

# --- AUTH & USERS ---

class UserBase(BaseModel):
    username: str
    role: UserRole = UserRole.OPERATOR
    stations: List['Station'] = [] # Changed to list of Station objects

class UserCreate(UserBase):
    pin: str # 4 digits
    station_codes: List[str] = [] # Codes of stations to associate

class UserUpdate(BaseModel):
    username: Optional[str] = None
    role: Optional[UserRole] = None
    pin: Optional[str] = None # Optional PIN reset
    station_codes: Optional[List[str]] = None

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
    issue_notes: Optional[str] = None
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

class PlanningIssue(BaseModel):
    notes: str

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

# --- MMG DIGITAL ---

import enum

class MMGStatus(str, enum.Enum):
    SENT = "SENT"
    IN_STUDY = "IN_STUDY"
    VALIDATED = "VALIDATED"
    IN_PRODUCTION = "IN_PRODUCTION"

class MMGStatusUpdate(BaseModel):
    status: MMGStatus

class MMGClient(BaseModel):
    name: str
    contact: str
    address: str
    site_address: Optional[str] = None
    email: str
    client_type: str = "PARTICULIER" # PRO / PARTICULIER

class MMGMeasurements(BaseModel):
    width_mm: float
    height_mm: float
    passage_height_mm: float

class MMGOptions(BaseModel):
    sill_height_mm: Optional[float] = None
    transom_height_mm: Optional[float] = None
    shutter_type: Optional[str] = None

class MMGConfiguration(BaseModel):
    view: str = "interior"
    opening_type: str
    opening_side: str
    sash_count: int
    material: Optional[str] = "ALU"
    product_series: Optional[str] = "Standard"
    color_ral: Optional[str] = "7016"
    is_bicolor: bool = False
    texture: Optional[str] = "Lisse"
    glazing_type: Optional[str] = "4/16/4"
    installation_type: Optional[str] = "Neuf"
    hardware_type: Optional[str] = "Standard"
    is_pmr_compliant: bool = False
    doublage_thickness: Optional[str] = "100" # For Neuf
    keep_existing_frame: bool = False # For Reno

class MMGLogistics(BaseModel):
    floor_number: int = 0
    access_difficulty: Optional[str] = "Standard"
    environment: Optional[str] = "Standard"

class MMGCreate(BaseModel):
    client: MMGClient
    measurements: MMGMeasurements
    options: MMGOptions
    configuration: MMGConfiguration
    logistics: Optional[MMGLogistics] = None
    photos: List[str]
    signature: str # Base64

class MMGResponse(BaseModel):
    id: int
    reference: str
    client_name: str
    status: MMGStatus
    created_at: datetime
    
    class Config:
        from_attributes = True

class MMGDetail(MMGResponse):
    client_contact: str
    client_address: str
    site_address: Optional[str]
    client_email: str
    client_type: str
    width: float
    height: float
    passage_height: float
    sill_height: Optional[float]
    transom_height: Optional[float]
    shutter_type: Optional[str]
    opening_type: str
    opening_side: str
    sash_count: int
    view_type: str
    material: Optional[str]
    product_series: Optional[str]
    color_ral: Optional[str]
    is_bicolor: bool
    texture: Optional[str]
    glazing_type: Optional[str]
    installation_type: Optional[str]
    hardware_type: Optional[str]
    is_pmr_compliant: bool
    doublage_thickness: Optional[str]
    keep_existing_frame: bool
    floor_number: int
    access_difficulty: Optional[str]
    environment: Optional[str]
    quote_sent_at: Optional[datetime]
    photos: List[str] # Will be list in response
    signature: str
    order_id: Optional[int]
    
    class Config:
        from_attributes = True
