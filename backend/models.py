from sqlalchemy import Column, Integer, String, Enum as SAEnum, DateTime, ForeignKey, Float, Boolean, Text, UniqueConstraint, Numeric, JSON
from sqlalchemy.orm import relationship
from .database import Base
from .core.time import utcnow
import enum


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
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    job_title = Column(String, nullable=True)
    team = Column(String, nullable=True)
    access_mode = Column(String, default="PIN") # PIN, EMAIL, HYBRID
    invitation_status = Column(String, default="ACTIVE") # ACTIVE, PENDING, SENT, FAILED
    invite_token = Column(String, nullable=True, unique=True, index=True)
    invited_at = Column(DateTime, nullable=True)
    pin_must_change = Column(Boolean, default=False)
    last_login_at = Column(DateTime, nullable=True)
    pin_hash = Column(String) # Hashed 4-digit PIN
    role = Column(String, default="OPERATOR") # Link to roles.name
    is_active = Column(Boolean, default=True)
    
    # Many-to-many relationship with Stations
    stations = relationship("Station", secondary="user_stations")
    secondary_roles = relationship("Role", secondary="user_secondary_roles")

    @property
    def additional_roles(self):
        return [role.name for role in self.secondary_roles or []]

    @property
    def role_names(self):
        names = [self.role] if self.role else []
        names.extend(role.name for role in self.secondary_roles or [] if role.name not in names)
        return names

class UserStation(Base):
    __tablename__ = "user_stations"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    station_id = Column(Integer, ForeignKey("stations.id"), primary_key=True)

class UserSecondaryRole(Base):
    __tablename__ = "user_secondary_roles"
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)

class Planning(Base):
    __tablename__ = "planning"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    station = Column(String) # Changed from Enum to String
    priority = Column(Integer, default=0) # Higher = More urgent
    status = Column(SAEnum(PlanningStatus), default=PlanningStatus.PENDING)
    issue_notes = Column(String, nullable=True)
    assigned_to = Column(String, nullable=True) # Name of the operator
    created_at = Column(DateTime, default=utcnow)

    order = relationship("Order")

    @property
    def order_reference(self):
        return self.order.reference if self.order else f"ORD-{self.order_id}"

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True) # Ex: CMD-XXXX
    sale_order_id = Column(Integer, ForeignKey("sale_orders.id"), nullable=True, index=True)
    sale_order_line_id = Column(Integer, ForeignKey("sale_order_lines.id"), nullable=True, index=True)
    width = Column(Float)
    height = Column(Float)
    material = Column(SAEnum(MaterialType))
    
    # New Fields
    client_name = Column(String, nullable=True)
    color = Column(String, nullable=True)
    quantity = Column(Integer, default=1)
    system_type = Column(String, nullable=True)
    
    logs = relationship("ProductionLog", back_populates="order")
    sale_order = relationship("SaleOrder")
    sale_order_line = relationship("SaleOrderLine")

class ProductionLog(Base):
    __tablename__ = "production_logs"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    station = Column(String) # Changed from Enum to String
    material = Column(String) # PVC or ALU
    operator_name = Column(String, nullable=True) # Who did the task
    start_time = Column(DateTime, default=utcnow)
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

# --- STOCK (V3 PIM) ---

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    reference_base = Column(String, unique=True, index=True) # Ex: VEK-70
    name = Column(String) # Ex: Dormant 70mm
    material_type = Column(String) # PVC, ALU, VITRAGE, ACCESSOIRE
    unit = Column(String) # ml, m2, pce
    supplier = Column(String, nullable=True)
    product_type = Column(String, default="stockable") # stockable, consumable, service
    available_in_pos = Column(Boolean, default=False)
    image_url = Column(String, nullable=True)
    technical_doc_url = Column(String, nullable=True) # Fiche technique PDF
    compatible_series = Column(String, nullable=True) # Ex: "COR 60, COR 70"
    catalog_status = Column(String, default="ACTIVE", index=True) # ACTIVE, DRAFT
    
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")

class ProductVariant(Base):
    __tablename__ = "product_variants"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    reference = Column(String, unique=True, index=True) # Ex: VEK-70-BLANC
    barcode = Column(String, unique=True, index=True, nullable=True) # Code-barres / EAN13
    color = Column(String, nullable=True)
    length_per_unit = Column(Float, nullable=True) # Ex: 6m pour barre ALU
    supplier_reference = Column(String, nullable=True)
    cost_price = Column(Numeric(14, 2), nullable=True)
    quantity_in_stock = Column(Float, default=0.0)
    min_threshold = Column(Float, default=10.0)
    image_url = Column(String, nullable=True)
    location = Column(String, nullable=True) # Ex: Rayon B3

    product = relationship("Product", back_populates="variants")
    quants = relationship("StockQuant", back_populates="variant", cascade="all, delete-orphan")
    moves = relationship("StockMove", back_populates="variant", cascade="all, delete-orphan")

    reserved_quantity = 0.0
    available_quantity = 0.0

# --- ODOO INVENTORY ENGINE ---
class StockLocation(Base):
    __tablename__ = "stock_locations"
    id = Column(Integer, primary_key=True, index=True)
    parent_id = Column(Integer, ForeignKey("stock_locations.id"), nullable=True)
    name = Column(String, index=True) # WH/Stock, Virtual/Inventory, Partner/Vendor
    usage = Column(String, default="internal") # internal, supplier, customer, inventory, production
    is_active = Column(Boolean, default=True)

    children = relationship("StockLocation", back_populates="parent", cascade="all, delete-orphan")
    parent = relationship("StockLocation", back_populates="children", remote_side=[id])

class StockQuant(Base):
    __tablename__ = "stock_quants"
    __table_args__ = (
        # Un seul quant par couple (variante, emplacement) : l'unicité arbitre
        # les créations concurrentes dans get_or_create_quant.
        UniqueConstraint("variant_id", "location_id", name="uq_stock_quants_variant_location"),
    )
    id = Column(Integer, primary_key=True, index=True)
    variant_id = Column(Integer, ForeignKey("product_variants.id"))
    location_id = Column(Integer, ForeignKey("stock_locations.id"))
    quantity = Column(Float, default=0.0)

    variant = relationship("ProductVariant")
    location = relationship("StockLocation")

class StockMove(Base):
    __tablename__ = "stock_moves"
    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, index=True) # e.g. WH/IN/0001
    date = Column(DateTime, default=utcnow)
    variant_id = Column(Integer, ForeignKey("product_variants.id"))
    location_id = Column(Integer, ForeignKey("stock_locations.id"), nullable=True) # Source
    location_dest_id = Column(Integer, ForeignKey("stock_locations.id"), nullable=True) # Dest
    quantity = Column(Float)
    state = Column(String, default="done")
    notes = Column(String, nullable=True)
    author = Column(String, default="Système")
    source_screen = Column(String, nullable=True)
    document_type = Column(String, nullable=True)
    document_reference = Column(String, nullable=True)
    business_reason = Column(String, nullable=True)

    variant = relationship("ProductVariant")
    source_location = relationship("StockLocation", foreign_keys=[location_id])
    dest_location = relationship("StockLocation", foreign_keys=[location_dest_id])

class StockReservation(Base):
    __tablename__ = "stock_reservations"
    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True)
    sale_order_id = Column(Integer, ForeignKey("sale_orders.id"), nullable=True, index=True)
    production_order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, index=True)
    order_reference = Column(String, index=True, nullable=True)
    project_reference = Column(String, index=True, nullable=True)
    source_label = Column(String, nullable=True)
    # Emplacement interne auquel la réservation est ancrée : le disponible est
    # calculé sur CET emplacement et la consommation puise depuis lui.
    location_id = Column(Integer, ForeignKey("stock_locations.id"), nullable=True, index=True)
    status = Column(String, default="reserved", index=True) # reserved, consumed, cancelled
    notes = Column(Text, nullable=True)
    created_by = Column(String, default="Système")
    created_at = Column(DateTime, default=utcnow)
    consumed_at = Column(DateTime, nullable=True)

    lines = relationship("StockReservationLine", back_populates="reservation", cascade="all, delete-orphan")
    sale_order = relationship("SaleOrder")
    production_order = relationship("Order")
    location = relationship("StockLocation")

class StockReservationLine(Base):
    __tablename__ = "stock_reservation_lines"
    id = Column(Integer, primary_key=True, index=True)
    reservation_id = Column(Integer, ForeignKey("stock_reservations.id"))
    variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=True)
    supplier = Column(String, nullable=True)
    supplier_reference = Column(String, nullable=True)
    designation = Column(String, nullable=True)
    unit = Column(String, nullable=True)
    requested_quantity = Column(Float, default=0.0)
    reserved_quantity = Column(Float, default=0.0)
    consumed_quantity = Column(Float, default=0.0)
    available_at_reservation = Column(Float, default=0.0)
    status = Column(String, default="reserved", index=True) # reserved, not_found, shortage, consumed, cancelled
    source = Column(String, nullable=True)

    reservation = relationship("StockReservation", back_populates="lines")
    variant = relationship("ProductVariant")

class InventorySession(Base):
    __tablename__ = "inventory_sessions"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True)
    name = Column(String, nullable=False)
    status = Column(String, default="draft", index=True) # draft, counting, validated, cancelled
    location_id = Column(Integer, ForeignKey("stock_locations.id"), nullable=True, index=True)
    notes = Column(Text, nullable=True)
    zone_locked = Column(Boolean, default=True)
    blind_counting = Column(Boolean, default=False) # comptage aveugle : espéré masqué jusqu'à validation
    locked_at = Column(DateTime, default=utcnow)
    unlocked_at = Column(DateTime, nullable=True)
    created_by = Column(String, default="Système")
    created_at = Column(DateTime, default=utcnow)
    validated_by = Column(String, nullable=True)
    validated_at = Column(DateTime, nullable=True)

    location = relationship("StockLocation")
    lines = relationship("InventoryCountLine", back_populates="session", cascade="all, delete-orphan")

class InventoryCountLine(Base):
    __tablename__ = "inventory_count_lines"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("inventory_sessions.id"), index=True)
    variant_id = Column(Integer, ForeignKey("product_variants.id"), index=True)
    location_id = Column(Integer, ForeignKey("stock_locations.id"), index=True)
    expected_quantity = Column(Float, default=0.0)
    counted_quantity = Column(Float, default=0.0)
    variance_quantity = Column(Float, default=0.0)
    status = Column(String, default="ok", index=True) # pending, ok, variance, recount, validated
    reason = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    recount_requested_by = Column(String, nullable=True)
    recount_requested_at = Column(DateTime, nullable=True)
    recount_notes = Column(Text, nullable=True)
    counted_by = Column(String, default="Système")
    counted_at = Column(DateTime, default=utcnow)
    adjustment_move_id = Column(Integer, ForeignKey("stock_moves.id"), nullable=True)

    session = relationship("InventorySession", back_populates="lines")
    variant = relationship("ProductVariant")
    location = relationship("StockLocation")
    adjustment_move = relationship("StockMove")

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

    # Configuration fine du formulaire (JSON) : forme, ventilation,
    # soubassement_type, doublage... + sous-clé "annexes" (volets,
    # moustiquaire, frais de pose, livraison). Source des plus-values du devis.
    configuration = Column(JSON, nullable=True)
    
    # Logistics
    floor_number = Column(Integer, default=0)
    access_difficulty = Column(String, nullable=True) # None, Crane, etc.
    environment = Column(String, default="Standard") # Standard, Coastal, Urban High-Rise
    
    photos = Column(String) # Comma separated filenames or JSON list
    signature = Column(String) # Path to signature image
    
    # Sales info
    quote_sent_at = Column(DateTime, nullable=True)
    sale_order_id = Column(Integer, ForeignKey("sale_orders.id"), nullable=True)
    
    status = Column(SAEnum(MMGStatus), default=MMGStatus.SENT)
    
    sale_order = relationship("SaleOrder", back_populates="mmg_dossiers")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    
    # Link to Order (once validated and imported)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    order = relationship("Order")

# --- REGLAGES & REFERENTIELS (CONFIG) ---
class AppConfig(Base):
    __tablename__ = "app_configs"
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, index=True)
    value = Column(String)

# --- CHATTER & AUDIT LOG ---
class ChatterMessage(Base):
    __tablename__ = "chatter_messages"
    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String, index=True) # e.g. "product", "variant", "location", "order"
    record_id = Column(Integer, index=True)
    body = Column(Text)
    author = Column(String)
    is_system_log = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)

# --- RBAC DIRECTORY ---
class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(String)
    permissions = relationship("Permission", secondary="role_permissions", backref="roles")

class Permission(Base):
    __tablename__ = "permissions"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    module = Column(String)
    description = Column(String)

class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)

# --- SALES & CRM (B2B) ---
class SaleOrder(Base):
    __tablename__ = "sale_orders"
    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True) # DEVIS-2026-0001
    client_name = Column(String)
    client_contact = Column(String, nullable=True)
    client_email = Column(String, nullable=True)
    client_address = Column(String, nullable=True)
    status = Column(String, default="DRAFT") # DRAFT, SENT, VALIDATED, CANCELLED, DELIVERED
    workflow_type = Column(String, default="FREE_SALE", index=True) # FREE_SALE, FABRICATION_ESTIMATE, FABRICATION_FROM_MEASURE
    validity_days = Column(Integer, default=30)
    tax_rate = Column(Float, default=18.0) # percentage
    currency = Column(String, default="EUR")
    notes = Column(Text, nullable=True)
    author = Column(String, default="Système")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    
    # E-Signature Portal
    signature_token = Column(String, unique=True, index=True, nullable=True)
    signed_at = Column(DateTime, nullable=True)
    signed_by_ip = Column(String, nullable=True)
    
    lines = relationship("SaleOrderLine", back_populates="order", cascade="all, delete-orphan")
    mmg_dossiers = relationship("MMG", back_populates="sale_order")

class SaleOrderLine(Base):
    __tablename__ = "sale_order_lines"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("sale_orders.id"))
    line_type = Column(String, default="SERVICE", index=True) # STOCK_ITEM, SERVICE
    variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=True) # None if custom line
    description = Column(String) # Derived from variant or custom input
    quantity = Column(Float, default=1.0)
    unit_price = Column(Numeric(14, 2), default=0.0) # HT
    discount_pct = Column(Float, default=0.0) # % discount
    visual_config = Column(Text, nullable=True) # JSON string for drawing
    
    order = relationship("SaleOrder", back_populates="lines")
    variant = relationship("ProductVariant")

# --- POINT OF SALE (B2C) ---
class POSSession(Base):
    __tablename__ = "pos_sessions"
    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True) # POS-S-0001
    opened_by_user = Column(String)
    opened_at = Column(DateTime, default=utcnow)
    closed_at = Column(DateTime, nullable=True)
    starting_cash = Column(Numeric(14, 2), default=0.0)
    closing_cash = Column(Numeric(14, 2), nullable=True)
    status = Column(String, default="OPEN") # OPEN, CLOSED
    
    orders = relationship("POSOrder", back_populates="session", cascade="all, delete-orphan")
    cash_movements = relationship("POSCashMovement", back_populates="session", cascade="all, delete-orphan")

class POSCashMovement(Base):
    __tablename__ = "pos_cash_movements"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("pos_sessions.id"))
    movement_type = Column(String) # IN, OUT
    amount = Column(Numeric(14, 2), default=0.0)
    reason = Column(String)
    author = Column(String)
    created_at = Column(DateTime, default=utcnow)
    
    session = relationship("POSSession", back_populates="cash_movements")

class POSOrder(Base):
    __tablename__ = "pos_orders"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("pos_sessions.id"))
    reference = Column(String, unique=True, index=True) # TK-2026-00001
    date = Column(DateTime, default=utcnow)
    payment_method = Column(String, default="CASH") # CASH, CB, MOBO
    tax_rate = Column(Float, default=18.0)
    currency = Column(String, default="EUR")
    amount_total = Column(Numeric(14, 2), default=0.0)
    amount_paid = Column(Numeric(14, 2), default=0.0)
    amount_return = Column(Numeric(14, 2), default=0.0)
    seller_name = Column(String, default="Admin")
    
    
    session = relationship("POSSession", back_populates="orders")
    lines = relationship("POSOrderLine", back_populates="order", cascade="all, delete-orphan")

class POSOrderLine(Base):
    __tablename__ = "pos_order_lines"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("pos_orders.id"))
    variant_id = Column(Integer, ForeignKey("product_variants.id"))
    product_name = Column(String) # Saved at time of checkout
    quantity = Column(Float, default=1.0)
    unit_price = Column(Numeric(14, 2), default=0.0) # HT
    
    order = relationship("POSOrder", back_populates="lines")
    variant = relationship("ProductVariant")

# --- CLIENTS (CRM) ---
class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    contact_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    tax_id = Column(String, nullable=True) # NIU
    customer_type = Column(String, default="B2B") # B2B, B2C
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)

# --- FOURNISSEURS (SUPPLIERS) ---
class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    contact_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    country = Column(String, nullable=True)
    tax_id = Column(String, nullable=True)
    supplier_status = Column(String, default="ACTIVE")
    supplier_category = Column(String, nullable=True)
    default_currency = Column(String, default="EUR")
    incoterm = Column(String, nullable=True)
    delivery_terms = Column(String, nullable=True)
    website = Column(String, nullable=True)
    payment_terms = Column(String, nullable=True)
    lead_time_days = Column(Integer, nullable=True)
    preferred_contact_method = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)

# --- ACHATS (PURCHASES) ---
class PurchaseOrderStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    PARTIAL = "PARTIAL"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"

class PurchaseRequestStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CONVERTED = "CONVERTED"
    CANCELLED = "CANCELLED"

class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"
    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True)
    supplier = Column(String)
    expected_date = Column(DateTime, nullable=True)
    status = Column(SAEnum(PurchaseRequestStatus), default=PurchaseRequestStatus.PENDING_APPROVAL)
    total_amount = Column(Numeric(14, 2), default=0.0)
    global_discount_percent = Column(Float, default=0.0)
    sensitivity_reason = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    requested_by = Column(String, default="Système")
    approved_by = Column(String, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejected_by = Column(String, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    converted_by = Column(String, nullable=True)
    converted_at = Column(DateTime, nullable=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    lines = relationship("PurchaseRequestLine", back_populates="request", cascade="all, delete-orphan")
    purchase_order = relationship("PurchaseOrder")

class PurchaseRequestLine(Base):
    __tablename__ = "purchase_request_lines"
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("purchase_requests.id"))
    variant_id = Column(Integer, ForeignKey("product_variants.id"))
    quantity = Column(Float, default=1.0)
    unit_price = Column(Numeric(14, 2), default=0.0)
    discount_percent = Column(Float, default=0.0)
    need_priority = Column(String, nullable=True)
    need_reason = Column(Text, nullable=True)

    request = relationship("PurchaseRequest", back_populates="lines")
    variant = relationship("ProductVariant")

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True) # Ex: PO-2026-0001
    supplier = Column(String)
    order_date = Column(DateTime, default=utcnow)
    expected_date = Column(DateTime, nullable=True)
    status = Column(SAEnum(PurchaseOrderStatus), default=PurchaseOrderStatus.DRAFT)
    total_amount = Column(Numeric(14, 2), default=0.0)
    global_discount_percent = Column(Float, default=0.0)
    notes = Column(Text, nullable=True)
    author = Column(String, default="Système")
    
    lines = relationship("PurchaseOrderLine", back_populates="order", cascade="all, delete-orphan")
    supplier_invoices = relationship("SupplierInvoice", back_populates="purchase_order", cascade="all, delete-orphan")
    supplier_reminders = relationship("SupplierReminder", back_populates="purchase_order", cascade="all, delete-orphan")

class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("purchase_orders.id"))
    variant_id = Column(Integer, ForeignKey("product_variants.id"))
    quantity = Column(Float, default=1.0)
    quantity_received = Column(Float, default=0.0)
    unit_price = Column(Numeric(14, 2), default=0.0)
    discount_percent = Column(Float, default=0.0)
    
    order = relationship("PurchaseOrder", back_populates="lines")
    variant = relationship("ProductVariant")

class SupplierInvoice(Base):
    __tablename__ = "supplier_invoices"
    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, index=True)
    supplier_reference = Column(String, nullable=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), index=True)
    supplier = Column(String)
    issue_date = Column(DateTime, default=utcnow)
    due_date = Column(DateTime, nullable=True)
    status = Column(String, default="TO_PAY", index=True) # TO_PAY, PARTIAL, PAID, CANCELLED
    subtotal = Column(Numeric(14, 2), default=0.0)
    discount_amount = Column(Numeric(14, 2), default=0.0)
    total_amount = Column(Numeric(14, 2), default=0.0)
    notes = Column(Text, nullable=True)
    author = Column(String, default="Système")

    purchase_order = relationship("PurchaseOrder", back_populates="supplier_invoices")
    lines = relationship("SupplierInvoiceLine", back_populates="invoice", cascade="all, delete-orphan")
    payments = relationship("SupplierPayment", back_populates="invoice", cascade="all, delete-orphan")

class SupplierInvoiceLine(Base):
    __tablename__ = "supplier_invoice_lines"
    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("supplier_invoices.id"))
    purchase_order_line_id = Column(Integer, ForeignKey("purchase_order_lines.id"), index=True)
    variant_id = Column(Integer, ForeignKey("product_variants.id"))
    description = Column(String)
    quantity = Column(Float, default=0.0)
    unit_price = Column(Numeric(14, 2), default=0.0)
    discount_percent = Column(Float, default=0.0)
    line_total = Column(Numeric(14, 2), default=0.0)

    invoice = relationship("SupplierInvoice", back_populates="lines")
    purchase_order_line = relationship("PurchaseOrderLine")
    variant = relationship("ProductVariant")

class SupplierPayment(Base):
    __tablename__ = "supplier_payments"
    id = Column(Integer, primary_key=True, index=True)
    supplier_invoice_id = Column(Integer, ForeignKey("supplier_invoices.id"), nullable=False, index=True)
    supplier = Column(String, index=True)
    amount = Column(Numeric(14, 2), default=0.0)
    method = Column(String, default="TRANSFER")
    reference = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    payment_date = Column(DateTime, default=utcnow)
    created_by = Column(String, default="Système")
    created_at = Column(DateTime, default=utcnow)

    invoice = relationship("SupplierInvoice", back_populates="payments")

class SupplierDispute(Base):
    __tablename__ = "supplier_disputes"
    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True)
    supplier = Column(String, index=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=True, index=True)
    supplier_invoice_id = Column(Integer, ForeignKey("supplier_invoices.id"), nullable=True, index=True)
    title = Column(String)
    description = Column(Text, nullable=True)
    category = Column(String, default="OTHER")  # DELAY, QUANTITY, QUALITY, PRICE, DOCUMENT, OTHER
    severity = Column(String, default="MEDIUM")  # LOW, MEDIUM, HIGH, BLOCKING
    status = Column(String, default="OPEN", index=True)  # OPEN, IN_PROGRESS, RESOLVED, CANCELLED
    expected_quantity = Column(Float, nullable=True)
    received_quantity = Column(Float, nullable=True)
    expected_unit_price = Column(Numeric(14, 2), nullable=True)
    invoiced_unit_price = Column(Numeric(14, 2), nullable=True)
    expected_action = Column(String, nullable=True)  # REDELIVER, CREDIT_NOTE, REPLACE, PRICE_CORRECTION, INFO
    due_date = Column(DateTime, nullable=True)
    blocks_receipt = Column(Boolean, default=False)
    blocks_payment = Column(Boolean, default=False)
    impact_summary = Column(Text, nullable=True)
    created_by = Column(String, default="Système")
    created_at = Column(DateTime, default=utcnow)
    closed_by = Column(String, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    resolution_notes = Column(Text, nullable=True)

    purchase_order = relationship("PurchaseOrder")
    supplier_invoice = relationship("SupplierInvoice")
    attachments = relationship("SupplierDisputeAttachment", back_populates="dispute", cascade="all, delete-orphan")
    events = relationship("SupplierDisputeEvent", back_populates="dispute", cascade="all, delete-orphan")

class SupplierDisputeAttachment(Base):
    __tablename__ = "supplier_dispute_attachments"
    id = Column(Integer, primary_key=True, index=True)
    dispute_id = Column(Integer, ForeignKey("supplier_disputes.id"), nullable=False, index=True)
    original_filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, default=0)
    uploaded_by = Column(String, default="Système")
    uploaded_at = Column(DateTime, default=utcnow)

    dispute = relationship("SupplierDispute", back_populates="attachments")

class SupplierDisputeEvent(Base):
    __tablename__ = "supplier_dispute_events"
    id = Column(Integer, primary_key=True, index=True)
    dispute_id = Column(Integer, ForeignKey("supplier_disputes.id"), nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    message = Column(Text, nullable=True)
    actor = Column(String, default="Système")
    created_at = Column(DateTime, default=utcnow)

    dispute = relationship("SupplierDispute", back_populates="events")

class SupplierReminder(Base):
    __tablename__ = "supplier_reminders"
    id = Column(Integer, primary_key=True, index=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False, index=True)
    supplier = Column(String, index=True)
    channel = Column(String, default="email")
    recipient = Column(String, nullable=True)
    cc = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    message = Column(Text, nullable=True)
    status = Column(String, default="PREPARED", index=True)  # PREPARED, SENT, SKIPPED, FAILED
    error_message = Column(Text, nullable=True)
    include_pdf = Column(Boolean, default=True)
    sent_at = Column(DateTime, nullable=True)
    created_by = Column(String, default="Système")
    created_at = Column(DateTime, default=utcnow)

    purchase_order = relationship("PurchaseOrder", back_populates="supplier_reminders")

# --- FACTURATION (FRANCE NF525) ---

class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True) # F-YYYY-XXXX
    sale_order_id = Column(Integer, ForeignKey("sale_orders.id"), nullable=True)
    client_name = Column(String)
    client_address = Column(String, nullable=True)
    client_siret = Column(String, nullable=True) # France Specific
    issue_date = Column(DateTime, default=utcnow)
    due_date = Column(DateTime)
    status = Column(String, default="DRAFT") # DRAFT, UNPAID, PARTIAL, PAID, AVOIR
    invoice_type = Column(String, default="FINAL", index=True) # DEPOSIT, FINAL, CREDIT_NOTE
    source_invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    delivery_note_id = Column(Integer, ForeignKey("delivery_notes.id"), nullable=True)
    return_move_id = Column(Integer, ForeignKey("stock_moves.id"), nullable=True)
    
    subtotal = Column(Numeric(14, 2), default=0.0)
    tax_rate = Column(Float, default=20.0) # French standard TVA
    tax_amount = Column(Numeric(14, 2), default=0.0)
    total = Column(Numeric(14, 2), default=0.0)
    
    qr_code_hash = Column(String, nullable=True) # Sceau anti-fraude HMAC-SHA256 (NF525)
    previous_seal = Column(String, nullable=True) # Sceau de la pièce précédente (chaînage NF525)
    
    lines = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")
    sale_order = relationship("SaleOrder")
    source_invoice = relationship("Invoice", remote_side=[id], foreign_keys=[source_invoice_id])
    delivery_note = relationship("DeliveryNote")
    return_move = relationship("StockMove")

    @property
    def source_invoice_reference(self):
        return self.source_invoice.reference if self.source_invoice else None

class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    description = Column(String)
    quantity = Column(Float, default=1.0)
    unit_price = Column(Numeric(14, 2))
    tax_rate = Column(Float, default=20.0)
    
    invoice = relationship("Invoice", back_populates="lines")

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    amount = Column(Numeric(14, 2))
    payment_date = Column(DateTime, default=utcnow)
    method = Column(String) # VIREMENT, CB, CHEQUE, ESPECES
    reference = Column(String, nullable=True) # Transaction ID
    
    invoice = relationship("Invoice", back_populates="payments")

# --- LOGISTIQUE & LIVRAISON ---
class DeliveryRoute(Base):
    __tablename__ = "delivery_routes"
    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True) # ROUTE-YYYY-XXXX
    driver_name = Column(String)
    vehicle = Column(String)
    planned_date = Column(DateTime)
    status = Column(String, default="PLANNED") # PLANNED, IN_TRANSIT, COMPLETED
    
    notes = relationship("DeliveryNote", back_populates="route")

class DeliveryNote(Base):
    __tablename__ = "delivery_notes"
    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True) # BL-YYYY-XXXX
    route_id = Column(Integer, ForeignKey("delivery_routes.id"), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    sale_order_id = Column(Integer, ForeignKey("sale_orders.id"), nullable=True)
    
    client_name = Column(String)
    delivery_address = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)
    
    status = Column(String, default="READY") # READY, ASSIGNED, IN_TRANSIT, DELIVERED, ISSUE
    signed_at = Column(DateTime, nullable=True)
    signature_path = Column(String, nullable=True) # Chemin relatif sous uploads/ de la signature client
    delivery_notes = Column(Text, nullable=True) # Changed from 'notes' to avoid name clash
    
    order = relationship("Order")
    sale_order = relationship("SaleOrder")
    route = relationship("DeliveryRoute", back_populates="notes")

class BusinessRule(Base):
    __tablename__ = "business_rules"
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, nullable=False) # PRODUCTION, PLANNING, COMMERCIAL, LOGISTIQUE
    rule_key = Column(String, unique=True, index=True, nullable=False)
    value = Column(String, nullable=False)
    value_type = Column(String, nullable=False) # number, string, boolean
    description = Column(String, nullable=True)

class DocumentSequence(Base):
    """Compteur transactionnel de numérotation des pièces commerciales (NF525).

    Une ligne par (doc_kind, année). L'incrément se fait par verrouillage de
    ligne (SELECT ... FOR UPDATE) dans la transaction courante — voir
    backend/services/document_sequences.py.
    """
    __tablename__ = "document_sequences"

    id = Column(Integer, primary_key=True, index=True)
    doc_kind = Column(String, nullable=False) # invoice, credit_note, quote, purchase_order, supplier_invoice, delivery_note, mmg
    year = Column(Integer, nullable=False)
    counter = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("doc_kind", "year", name="uq_document_sequences_kind_year"),
    )
