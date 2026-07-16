from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime
from .models import MaterialType, StationName, UserRole, PlanningStatus

# --- AUTH & USERS ---

class UserBase(BaseModel):
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str = "OPERATOR"
    stations: List['Station'] = [] # Changed to list of Station objects

class UserCreate(UserBase):
    pin: str # 4 digits
    station_codes: List[str] = [] # Codes of stations to associate

class UserUpdate(BaseModel):
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    pin: Optional[str] = None # Optional PIN reset
    station_codes: Optional[List[str]] = None

class User(UserBase):
    id: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# --- PARTNERS (CLIENTS / FOURNISSEURS) ---
class ClientBase(BaseModel):
    name: str
    contact_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    tax_id: Optional[str] = None
    customer_type: str = "B2B"
    is_active: bool = True

class ClientCreate(ClientBase):
    pass

class ClientResponse(ClientBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class SupplierBase(BaseModel):
    name: str
    contact_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    tax_id: Optional[str] = None
    is_active: bool = True

class SupplierCreate(SupplierBase):
    pass

class SupplierResponse(SupplierBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# --- PLANNING ---

class PlanningBase(BaseModel):
    station: str # Changed from StationName enum to str
    priority: int = 0
    status: PlanningStatus = PlanningStatus.PENDING
    issue_notes: Optional[str] = None
    assigned_to: Optional[str] = None

class PlanningCreate(PlanningBase):
    order_reference: str

class Planning(PlanningBase):
    id: int
    order_id: int
    order_reference: Optional[str] = None
    order: Optional['Order'] = None
    issue_notes: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# --- LOGS ---

class ProductionLogBase(BaseModel):
    station: str # Changed from StationName enum to str
    operator_name: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[int] = None

class ProductionLog(ProductionLogBase):
    id: int
    order_id: int

    model_config = ConfigDict(from_attributes=True)

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
    sale_order_id: Optional[int] = None
    sale_order_line_id: Optional[int] = None
    client_name: Optional[str] = None
    color: Optional[str] = None
    quantity: int = 1
    system_type: Optional[str] = None

class OrderCreate(OrderBase):
    pass

class Order(OrderBase):
    id: int
    logs: List[ProductionLog] = []

    model_config = ConfigDict(from_attributes=True)

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
    model_config = ConfigDict(from_attributes=True)

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
    sale_order_id: Optional[int] = None
    photos: List[str]
    signature: str # Base64

class MMGResponse(BaseModel):
    id: int
    reference: str
    client_name: str
    status: MMGStatus
    sale_order_id: Optional[int] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

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
    
    model_config = ConfigDict(from_attributes=True)

# --- STOCK V3 PIM ---
from typing import List

class ProductVariantBase(BaseModel):
    reference: str
    barcode: Optional[str] = None
    color: Optional[str] = None
    length_per_unit: Optional[float] = None
    supplier_reference: Optional[str] = None
    cost_price: Optional[float] = None
    quantity_in_stock: float = 0.0
    min_threshold: float = 10.0
    image_url: Optional[str] = None
    location: Optional[str] = None

class ProductVariantCreate(ProductVariantBase):
    pass

class ProductVariantResponse(ProductVariantBase):
    id: int
    product_id: int
    reserved_quantity: float = 0.0
    available_quantity: float = 0.0
    model_config = ConfigDict(from_attributes=True)

class ProductBase(BaseModel):
    reference_base: str
    name: str
    material_type: str
    unit: str
    supplier: Optional[str] = None
    product_type: str = "stockable"
    available_in_pos: bool = False
    image_url: Optional[str] = None
    technical_doc_url: Optional[str] = None
    compatible_series: Optional[str] = None
    catalog_status: str = "ACTIVE"

class ProductCreate(ProductBase):
    variants: List[ProductVariantCreate] = []

class ProductResponse(ProductBase):
    id: int
    variants: List[ProductVariantResponse] = []
    model_config = ConfigDict(from_attributes=True)

class StockLocationBase(BaseModel):
    name: str
    usage: str = "internal" # internal, supplier, customer, inventory
    parent_id: Optional[int] = None
    is_active: bool = True

class StockLocationCreate(StockLocationBase):
    pass

class StockLocationUpdate(BaseModel):
    name: Optional[str] = None
    usage: Optional[str] = None
    parent_id: Optional[int] = None
    is_active: Optional[bool] = None

class StockLocationResponse(StockLocationBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class StockQuantBase(BaseModel):
    variant_id: int
    location_id: int
    quantity: float

class StockQuantResponse(StockQuantBase):
    id: int
    location: StockLocationResponse
    model_config = ConfigDict(from_attributes=True)

class StockMoveCreate(BaseModel):
    variant_id: int
    location_id: Optional[int] = None # Source
    location_dest_id: Optional[int] = None # Dest
    quantity: float
    notes: Optional[str] = None

class StockMoveResponse(BaseModel):
    id: int
    reference: str
    variant_id: int
    quantity: float
    date: datetime
    state: str
    author: Optional[str] = None
    location_id: Optional[int] = None
    location_dest_id: Optional[int] = None
    notes: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class StockReservationLineResponse(BaseModel):
    id: int
    variant_id: Optional[int] = None
    supplier: Optional[str] = None
    supplier_reference: Optional[str] = None
    designation: Optional[str] = None
    unit: Optional[str] = None
    requested_quantity: float
    reserved_quantity: float
    consumed_quantity: float
    available_at_reservation: float
    status: str
    source: Optional[str] = None
    variant: Optional[ProductVariantResponse] = None
    model_config = ConfigDict(from_attributes=True)

class StockReservationResponse(BaseModel):
    id: int
    reference: str
    sale_order_id: Optional[int] = None
    production_order_id: Optional[int] = None
    order_reference: Optional[str] = None
    project_reference: Optional[str] = None
    source_label: Optional[str] = None
    status: str
    notes: Optional[str] = None
    created_by: str
    created_at: datetime
    consumed_at: Optional[datetime] = None
    lines: List[StockReservationLineResponse] = []
    model_config = ConfigDict(from_attributes=True)

class WorkshopDebitPreviewResponse(BaseModel):
    summary: dict
    issues: list
    records: list
    stock_matches: list

class InventorySessionCreate(BaseModel):
    name: str
    location_id: Optional[int] = None
    notes: Optional[str] = None
    zone_locked: bool = True

class InventoryCountLineUpsert(BaseModel):
    variant_id: int
    location_id: int
    counted_quantity: float
    reason: Optional[str] = None
    notes: Optional[str] = None

class InventoryCountLineResponse(BaseModel):
    id: int
    session_id: int
    variant_id: int
    location_id: int
    expected_quantity: float
    counted_quantity: float
    variance_quantity: float
    status: str = "ok"
    reason: Optional[str] = None
    notes: Optional[str] = None
    recount_requested_by: Optional[str] = None
    recount_requested_at: Optional[datetime] = None
    recount_notes: Optional[str] = None
    counted_by: str
    counted_at: datetime
    adjustment_move_id: Optional[int] = None
    variant: Optional[ProductVariantResponse] = None
    location: Optional[StockLocationResponse] = None
    model_config = ConfigDict(from_attributes=True)

class InventorySessionResponse(BaseModel):
    id: int
    reference: str
    name: str
    status: str
    location_id: Optional[int] = None
    notes: Optional[str] = None
    zone_locked: bool = True
    locked_at: Optional[datetime] = None
    unlocked_at: Optional[datetime] = None
    created_by: str
    created_at: datetime
    validated_by: Optional[str] = None
    validated_at: Optional[datetime] = None
    location: Optional[StockLocationResponse] = None
    lines: List[InventoryCountLineResponse] = []
    model_config = ConfigDict(from_attributes=True)

class InventoryRecountRequest(BaseModel):
    notes: Optional[str] = None

# --- REGLAGES & REFERENTIELS (CONFIG) ---
class AppConfigBase(BaseModel):
    category: str
    value: str

class AppConfigCreate(AppConfigBase):
    pass

class AppConfigResponse(AppConfigBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# --- CHATTER (AUDIT LOG) ---
class ChatterMessageBase(BaseModel):
    model_name: str
    record_id: int
    body: str
    is_system_log: bool = False

class ChatterMessageCreate(ChatterMessageBase):
    pass

class ChatterMessageResponse(ChatterMessageBase):
    id: int
    author: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# --- RBAC ---

class PermissionSchema(BaseModel):
    id: int
    code: str
    module: str
    description: str
    model_config = ConfigDict(from_attributes=True)

class RoleCreate(BaseModel):
    name: str
    description: str

class RoleSchema(BaseModel):
    id: int
    name: str
    description: str
    permissions: List[PermissionSchema] = []
    model_config = ConfigDict(from_attributes=True)

# --- SALES & POS ---

class POSOrderLineSchema(BaseModel):
    id: int
    variant_id: int
    product_name: str
    quantity: float
    unit_price: float
    model_config = ConfigDict(from_attributes=True)

class POSOrderSchema(BaseModel):
    id: int
    session_id: int
    reference: str
    date: datetime
    payment_method: str
    tax_rate: float
    currency: str
    amount_total: float
    amount_paid: float
    amount_return: float
    lines: List[POSOrderLineSchema] = []
    model_config = ConfigDict(from_attributes=True)

class POSSessionSchema(BaseModel):
    id: int
    reference: str
    opened_by_user: str
    opened_at: datetime
    closed_at: Optional[datetime]
    starting_cash: float
    closing_cash: Optional[float]
    status: str
    orders: List[POSOrderSchema] = []
    model_config = ConfigDict(from_attributes=True)

class POSCartItem(BaseModel):
    variant_id: int
    quantity: float
    price: float
    product_name: str

class POSCheckoutRequest(BaseModel):
    items: List[POSCartItem]
    payment_method: str # CASH, CB, MOBO
    amount_paid: float
    tax_rate: float = 18.0
    currency: str = "EUR"

# B2B CRM

class SaleOrderLineCreate(BaseModel):
    line_type: Optional[str] = None
    variant_id: Optional[int] = None
    description: str
    quantity: float
    unit_price: float
    discount_pct: float = 0.0
    visual_config: Optional[str] = None

class SaleOrderCreate(BaseModel):
    client_name: str
    client_contact: Optional[str] = None
    client_email: Optional[str] = None
    client_address: Optional[str] = None
    workflow_type: str = "FREE_SALE"
    validity_days: int = 30
    tax_rate: float = 18.0
    currency: str = "EUR"
    notes: Optional[str] = None
    lines: List[SaleOrderLineCreate]

class SaleOrderLineSchema(BaseModel):
    id: int
    line_type: str = "SERVICE"
    variant_id: Optional[int]
    description: str
    quantity: float
    unit_price: float
    discount_pct: float
    visual_config: Optional[str] = None
    variant: Optional[ProductVariantResponse] = None
    reserved_quantity: float = 0.0
    available_quantity: float = 0.0
    model_config = ConfigDict(from_attributes=True)

class SaleInvoiceSummary(BaseModel):
    id: int
    reference: str
    issue_date: datetime
    status: str
    invoice_type: str = "FINAL"
    total: float
    source_invoice_id: Optional[int] = None
    source_invoice_reference: Optional[str] = None
    delivery_note_id: Optional[int] = None
    return_move_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)

class SaleDeliveryNoteSummary(BaseModel):
    id: int
    reference: str
    status: str
    signed_at: Optional[datetime] = None
    delivery_notes: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class SaleWorkshopStepSummary(BaseModel):
    id: int
    station: str
    status: str
    priority: int = 0
    assigned_to: Optional[str] = None
    issue_notes: Optional[str] = None
    created_at: Optional[datetime] = None

class SaleProductionOrderSummary(BaseModel):
    id: int
    reference: str
    material: Optional[str] = None
    width: Optional[float] = None
    height: Optional[float] = None
    quantity: int = 1
    color: Optional[str] = None
    system_type: Optional[str] = None
    steps: List[SaleWorkshopStepSummary] = []

class SaleOrderSchema(BaseModel):
    id: int
    reference: str
    client_name: str
    client_contact: Optional[str]
    client_email: Optional[str]
    client_address: Optional[str]
    status: str
    workflow_type: str = "FREE_SALE"
    validity_days: int
    tax_rate: float
    currency: str
    notes: Optional[str]
    author: str
    created_at: datetime
    updated_at: datetime
    signature_token: Optional[str]
    signed_at: Optional[datetime]
    signed_by_ip: Optional[str]
    lines: List[SaleOrderLineSchema] = []
    mmg_dossiers: List[MMGResponse] = []
    reservations: List[StockReservationResponse] = []
    invoices: List[SaleInvoiceSummary] = []
    delivery_notes: List[SaleDeliveryNoteSummary] = []
    production_orders: List[SaleProductionOrderSummary] = []
    model_config = ConfigDict(from_attributes=True)

# --- FACTURATION ---
class PaymentBase(BaseModel):
    amount: float
    method: str
    reference: Optional[str] = None

class PaymentCreate(PaymentBase):
    pass

class PaymentResponse(PaymentBase):
    id: int
    payment_date: datetime
    model_config = ConfigDict(from_attributes=True)

class InvoiceLineBase(BaseModel):
    description: str
    quantity: float
    unit_price: float
    tax_rate: float = 20.0

class InvoiceBase(BaseModel):
    client_name: str
    client_address: Optional[str] = None
    client_siret: Optional[str] = None
    due_date: datetime
    
class InvoiceCreate(InvoiceBase):
    sale_order_id: Optional[int] = None
    invoice_type: str = "FINAL"
    lines: List[InvoiceLineBase]

class CreditNoteCreate(BaseModel):
    delivery_note_id: Optional[int] = None

class InvoiceLineResponse(InvoiceLineBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class InvoiceResponse(InvoiceBase):
    id: int
    reference: str
    sale_order_id: Optional[int] = None
    invoice_type: str = "FINAL"
    source_invoice_id: Optional[int] = None
    source_invoice_reference: Optional[str] = None
    delivery_note_id: Optional[int] = None
    return_move_id: Optional[int] = None
    issue_date: datetime
    status: str
    subtotal: float
    tax_rate: float
    tax_amount: float
    total: float
    qr_code_hash: Optional[str] = None
    lines: List[InvoiceLineResponse] = []
    payments: List[PaymentResponse] = []
    model_config = ConfigDict(from_attributes=True)

# --- LOGISTIQUE & LIVRAISON ---
class DeliveryNoteBase(BaseModel):
    order_id: Optional[int] = None
    sale_order_id: Optional[int] = None
    client_name: str
    delivery_address: Optional[str] = None
    contact_phone: Optional[str] = None
    status: str = "READY"
    delivery_notes: Optional[str] = None

class DeliveryNoteCreate(DeliveryNoteBase):
    pass

class DeliveryNoteResponse(DeliveryNoteBase):
    id: int
    reference: str
    route_id: Optional[int] = None
    signed_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

class DeliveryRouteBase(BaseModel):
    driver_name: str
    vehicle: str
    planned_date: datetime
    status: str = "PLANNED"

class DeliveryRouteCreate(DeliveryRouteBase):
    note_ids: List[int] = [] # Delivery notes to assign

class DeliveryRouteResponse(DeliveryRouteBase):
    id: int
    reference: str
    notes: List[DeliveryNoteResponse] = []
    
    model_config = ConfigDict(from_attributes=True)

# --- POINT DE VENTE (POS) ---
class POSCashMovementRequest(BaseModel):
    movement_type: str # IN, OUT
    amount: float
    reason: str
    author: str = "Admin"

class POSCashMovementSchema(BaseModel):
    id: int
    session_id: int
    movement_type: str
    amount: float
    reason: str
    author: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class POSInvoicePaymentReq(BaseModel):
    amount: float
    method: str = "CASH"
    author: str = "Admin"

class POSSessionSchema(BaseModel):
    id: int
    reference: str
    opened_by_user: str
    opened_at: datetime
    closed_at: Optional[datetime] = None
    starting_cash: float
    closing_cash: Optional[float] = None
    status: str
    model_config = ConfigDict(from_attributes=True)

class POSCartItem(BaseModel):
    variant_id: int
    product_name: str
    quantity: float
    price: float

class POSCheckoutRequest(BaseModel):
    items: List[POSCartItem]
    payment_method: str = "CASH"
    amount_paid: float
    tax_rate: float = 20.0
    currency: str = "EUR"
    seller_name: Optional[str] = "Admin"

class POSOrderLineSchema(BaseModel):
    id: int
    variant_id: Optional[int]
    product_name: str
    quantity: float
    unit_price: float
    model_config = ConfigDict(from_attributes=True)

class POSOrderSchema(BaseModel):
    id: int
    session_id: int
    reference: str
    date: datetime
    payment_method: str
    tax_rate: float
    amount_total: float
    amount_paid: float
    amount_return: float
    lines: List[POSOrderLineSchema] = []
    model_config = ConfigDict(from_attributes=True)

class BusinessRuleBase(BaseModel):
    category: str
    rule_key: str
    value: str
    value_type: str
    description: Optional[str] = None

class BusinessRuleCreate(BusinessRuleBase):
    pass

class BusinessRuleUpdate(BaseModel):
    value: str

class BusinessRuleSchema(BusinessRuleBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class SMTPTestRequest(BaseModel):
    host: str
    port: int
    username: str
    password: str
    recipient: str

UserBase.model_rebuild()
User.model_rebuild()
UserCreate.model_rebuild()
UserUpdate.model_rebuild()
