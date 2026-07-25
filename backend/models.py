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
    category = Column(String, nullable=True, index=True) # PROFIL, ACCESSOIRE, QUINCAILLERIE...
    material_type = Column(String) # ALU, PVC, ACIER, VERRE...
    unit = Column(String) # ml, m2, pce
    supplier = Column(String, nullable=True)
    product_type = Column(String, default="stockable") # stockable, consumable, service
    available_in_pos = Column(Boolean, default=False)
    image_url = Column(String, nullable=True)
    technical_doc_url = Column(String, nullable=True) # Fiche technique PDF
    compatible_series = Column(String, nullable=True) # Ex: "COR 60, COR 70"
    catalog_status = Column(String, default="DRAFT", index=True) # DRAFT, TO_QUALIFY, ACTIVE, BLOCKED, ARCHIVED
    
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")

class ProductVariant(Base):
    __tablename__ = "product_variants"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    reference = Column(String, unique=True, index=True) # Ex: VEK-70-BLANC
    barcode = Column(String, unique=True, index=True, nullable=True) # Code-barres / EAN13
    color = Column(String, nullable=True)
    finish = Column(String, nullable=True)
    length_per_unit = Column(Float, nullable=True) # Ex: 6m pour barre ALU
    conditioning = Column(String, nullable=True) # unité, boîte, palette, rouleau...
    units_per_package = Column(Float, nullable=True)
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


class ProductAuditLog(Base):
    __tablename__ = "product_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String, nullable=False, index=True)
    changes = Column(JSON, nullable=True)
    reason = Column(Text, nullable=True)
    author = Column(String, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False, index=True)

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


class WorkshopPreparation(Base):
    __tablename__ = "workshop_preparations"
    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True, nullable=False)
    reservation_id = Column(Integer, ForeignKey("stock_reservations.id"), unique=True, index=True, nullable=False)
    sale_order_id = Column(Integer, ForeignKey("sale_orders.id"), nullable=True, index=True)
    production_order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, index=True)
    source_location_id = Column(Integer, ForeignKey("stock_locations.id"), nullable=False, index=True)
    destination_location_id = Column(Integer, ForeignKey("stock_locations.id"), nullable=False, index=True)
    status = Column(String, default="draft", index=True)  # draft, ready, handed_over, consumed, returned, cancelled
    notes = Column(Text, nullable=True)
    created_by = Column(String, default="Système")
    created_at = Column(DateTime, default=utcnow)
    handed_over_by = Column(String, nullable=True)
    handed_over_at = Column(DateTime, nullable=True)
    returned_by = Column(String, nullable=True)
    returned_at = Column(DateTime, nullable=True)

    reservation = relationship("StockReservation")
    sale_order = relationship("SaleOrder")
    production_order = relationship("Order")
    source_location = relationship("StockLocation", foreign_keys=[source_location_id])
    destination_location = relationship("StockLocation", foreign_keys=[destination_location_id])
    lines = relationship("WorkshopPreparationLine", back_populates="preparation", cascade="all, delete-orphan")


class WorkshopPreparationLine(Base):
    __tablename__ = "workshop_preparation_lines"
    id = Column(Integer, primary_key=True, index=True)
    preparation_id = Column(Integer, ForeignKey("workshop_preparations.id"), index=True, nullable=False)
    reservation_line_id = Column(Integer, ForeignKey("stock_reservation_lines.id"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=False, index=True)
    planned_quantity = Column(Float, default=0.0)
    prepared_quantity = Column(Float, default=0.0)
    transferred_quantity = Column(Float, default=0.0)
    returned_quantity = Column(Float, default=0.0)
    status = Column(String, default="pending", index=True)  # pending, prepared, handed_over, consumed, returned

    preparation = relationship("WorkshopPreparation", back_populates="lines")
    reservation_line = relationship("StockReservationLine")
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

class MeasureMissionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    TO_SCHEDULE = "TO_SCHEDULE"
    SCHEDULED = "SCHEDULED"
    IN_CAPTURE = "IN_CAPTURE"
    ON_SITE = "ON_SITE"
    TO_REVIEW = "TO_REVIEW"
    CORRECTION_REQUIRED = "CORRECTION_REQUIRED"
    VALIDATED = "VALIDATED"
    QUOTED = "QUOTED"
    CANCELLED = "CANCELLED"

class MMG(Base):
    __tablename__ = "mmg_dossiers"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True) # MMG-2026-XXXXX
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    site_address_id = Column(Integer, ForeignKey("client_site_addresses.id"), nullable=True, index=True)
    measure_mission_id = Column(Integer, ForeignKey("measure_missions.id"), nullable=True, index=True)
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
    client = relationship("Client", foreign_keys=[client_id])
    site_location = relationship("ClientSiteAddress", foreign_keys=[site_address_id])
    measure_mission = relationship(
        "MeasureMission",
        back_populates="dossiers",
        foreign_keys=[measure_mission_id],
    )
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
    country = Column(String, default="FR")
    tax_id = Column(String, nullable=True) # NIU
    customer_type = Column(String, default="B2B") # B2B, B2C
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    site_addresses = relationship(
        "ClientSiteAddress",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    measure_missions = relationship("MeasureMission", back_populates="client")
    opportunities = relationship(
        "CRMOpportunity",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    crm_activities = relationship(
        "CRMActivity",
        back_populates="client",
        cascade="all, delete-orphan",
    )


class ClientSiteAddress(Base):
    __tablename__ = "client_site_addresses"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(String, default="Chantier")
    address_line1 = Column(String, nullable=False)
    address_line2 = Column(String, nullable=True)
    postal_code = Column(String, nullable=True)
    city = Column(String, nullable=True)
    country = Column(String, default="FR")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    contact_name = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)
    access_instructions = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    client = relationship("Client", back_populates="site_addresses")
    measure_missions = relationship("MeasureMission", back_populates="site")
    opportunities = relationship("CRMOpportunity", back_populates="site")

    @property
    def formatted_address(self):
        locality = " ".join(part for part in [self.postal_code, self.city] if part)
        return ", ".join(
            part
            for part in [self.address_line1, self.address_line2, locality, self.country]
            if part
        )


class CRMOpportunityStage(str, enum.Enum):
    NEW = "nouveau"
    QUALIFIED = "qualifie"
    MEASURE_TO_SCHEDULE = "metre_a_planifier"
    MEASURE_IN_PROGRESS = "metre_en_cours"
    PROPOSAL_TO_PREPARE = "proposition_a_preparer"
    PROPOSAL_SENT = "proposition_envoyee"
    NEGOTIATION = "negociation"
    WON = "gagne"
    LOST = "perdu"


class CRMNeedType(str, enum.Enum):
    SUPPLY_AND_INSTALL = "fourniture_pose"
    SUPPLY_ONLY = "fourniture_seule"
    AFTER_SALES = "sav"
    OTHER = "autre"


class CRMActivityType(str, enum.Enum):
    CALL = "appel"
    EMAIL = "email"
    MEETING = "rendez_vous"
    NOTE = "note"
    TASK = "tache"


class CRMActivityStatus(str, enum.Enum):
    TODO = "a_faire"
    COMPLETED = "termine"
    CANCELLED = "annule"


class CRMOpportunity(Base):
    __tablename__ = "crm_opportunities"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, nullable=False, index=True)
    client_id = Column(
        Integer,
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_address_id = Column(
        Integer,
        ForeignKey("client_site_addresses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sale_order_id = Column(
        Integer,
        ForeignKey("sale_orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title = Column(String, nullable=False)
    origin = Column(String, nullable=True, index=True)
    need_type = Column(
        String,
        default=CRMNeedType.OTHER.value,
        nullable=False,
        index=True,
    )
    stage = Column(
        String,
        default=CRMOpportunityStage.NEW.value,
        nullable=False,
        index=True,
    )
    estimated_amount = Column(Numeric(14, 2), nullable=True)
    probability = Column(Integer, default=10, nullable=False)
    next_milestone = Column(String, nullable=True)
    next_milestone_at = Column(DateTime, nullable=True, index=True)
    expected_close_date = Column(DateTime, nullable=True)
    loss_reason = Column(Text, nullable=True)
    stage_entered_at = Column(DateTime, default=utcnow, nullable=False, index=True)
    won_at = Column(DateTime, nullable=True)
    lost_at = Column(DateTime, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    client = relationship("Client", back_populates="opportunities")
    site = relationship("ClientSiteAddress", back_populates="opportunities")
    owner = relationship("User")
    sale_order = relationship("SaleOrder")
    measure_missions = relationship(
        "MeasureMission",
        back_populates="opportunity",
        passive_deletes=True,
    )
    activities = relationship(
        "CRMActivity",
        back_populates="opportunity",
        passive_deletes=True,
    )
    reminder_plans = relationship(
        "CRMReminderPlan",
        back_populates="opportunity",
        passive_deletes=True,
    )

    @property
    def client_name(self):
        return self.client.name if self.client else None

    @property
    def site_reference(self):
        return self.site.reference if self.site else None

    @property
    def owner_name(self):
        if not self.owner:
            return None
        full_name = " ".join(
            part for part in [self.owner.first_name, self.owner.last_name] if part
        )
        return full_name or self.owner.username


class CRMActivity(Base):
    __tablename__ = "crm_activities"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(
        Integer,
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    opportunity_id = Column(
        Integer,
        ForeignKey("crm_opportunities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    activity_type = Column(String, nullable=False, index=True)
    subject = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    due_at = Column(DateTime, nullable=True, index=True)
    status = Column(
        String,
        default=CRMActivityStatus.TODO.value,
        nullable=False,
        index=True,
    )
    author = Column(String, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    client = relationship("Client", back_populates="crm_activities")
    opportunity = relationship("CRMOpportunity", back_populates="activities")

    @property
    def client_name(self):
        return self.client.name if self.client else None

    @property
    def opportunity_reference(self):
        return self.opportunity.reference if self.opportunity else None


class CRMReminderTemplate(Base):
    __tablename__ = "crm_reminder_templates"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    subject_template = Column(String, nullable=False)
    body_template = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_by = Column(String, default="Système", nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    deliveries = relationship("CRMReminderDelivery", back_populates="template")
    rules = relationship("CRMReminderRule", back_populates="template")


class CRMReminderRule(Base):
    __tablename__ = "crm_reminder_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    stage = Column(String, unique=True, nullable=False, index=True)
    delay_days = Column(Integer, default=2, nullable=False)
    template_id = Column(
        Integer,
        ForeignKey("crm_reminder_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assignment_strategy = Column(
        String,
        default="OPPORTUNITY_OWNER",
        nullable=False,
        index=True,
    )
    fixed_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_by = Column(String, default="Système", nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    template = relationship("CRMReminderTemplate", back_populates="rules")
    fixed_user = relationship("User")
    plans = relationship(
        "CRMReminderPlan",
        back_populates="rule",
        passive_deletes=True,
    )

    @property
    def template_name(self):
        return self.template.name if self.template else None

    @property
    def fixed_user_name(self):
        if not self.fixed_user:
            return None
        full_name = " ".join(
            part
            for part in [self.fixed_user.first_name, self.fixed_user.last_name]
            if part
        )
        return full_name or self.fixed_user.username


class CRMReminderPlan(Base):
    __tablename__ = "crm_reminder_plans"

    id = Column(Integer, primary_key=True, index=True)
    plan_key = Column(String, unique=True, nullable=False, index=True)
    rule_id = Column(
        Integer,
        ForeignKey("crm_reminder_rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    opportunity_id = Column(
        Integer,
        ForeignKey("crm_opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id = Column(
        Integer,
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sent_delivery_id = Column(
        Integer,
        ForeignKey("crm_reminder_deliveries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    stage_snapshot = Column(String, nullable=False, index=True)
    due_at = Column(DateTime, nullable=False, index=True)
    status = Column(String, default="PENDING", nullable=False, index=True)
    cancelled_reason = Column(Text, nullable=True)
    created_by = Column(String, default="Système", nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    rule = relationship("CRMReminderRule", back_populates="plans")
    opportunity = relationship("CRMOpportunity", back_populates="reminder_plans")
    client = relationship("Client")
    assigned_user = relationship("User")
    sent_delivery = relationship("CRMReminderDelivery")

    @property
    def client_name(self):
        return self.client.name if self.client else None

    @property
    def client_email(self):
        return self.client.email if self.client else None

    @property
    def opportunity_reference(self):
        return self.opportunity.reference if self.opportunity else None

    @property
    def opportunity_title(self):
        return self.opportunity.title if self.opportunity else None

    @property
    def assigned_user_name(self):
        if not self.assigned_user:
            return None
        full_name = " ".join(
            part
            for part in [self.assigned_user.first_name, self.assigned_user.last_name]
            if part
        )
        return full_name or self.assigned_user.username

    @property
    def template_id(self):
        return self.rule.template_id if self.rule else None

    @property
    def rule_name(self):
        return self.rule.name if self.rule else None


class CRMReminderDelivery(Base):
    __tablename__ = "crm_reminder_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    reminder_key = Column(String, nullable=True, index=True)
    client_id = Column(
        Integer,
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    opportunity_id = Column(
        Integer,
        ForeignKey("crm_opportunities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    template_id = Column(
        Integer,
        ForeignKey("crm_reminder_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    activity_id = Column(
        Integer,
        ForeignKey("crm_activities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    recipient = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String, default="PREPARED", nullable=False, index=True)
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_by = Column(String, default="Système", nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    client = relationship("Client")
    opportunity = relationship("CRMOpportunity")
    template = relationship("CRMReminderTemplate", back_populates="deliveries")
    activity = relationship("CRMActivity")

    @property
    def client_name(self):
        return self.client.name if self.client else None

    @property
    def opportunity_reference(self):
        return self.opportunity.reference if self.opportunity else None

    @property
    def template_name(self):
        return self.template.name if self.template else None


class MeasureMission(Base):
    __tablename__ = "measure_missions"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    site_address_id = Column(Integer, ForeignKey("client_site_addresses.id"), nullable=True, index=True)
    opportunity_id = Column(
        Integer,
        ForeignKey("crm_opportunities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sale_order_id = Column(Integer, ForeignKey("sale_orders.id"), nullable=True, index=True)
    assigned_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    status = Column(String, default=MeasureMissionStatus.DRAFT.value, nullable=False, index=True)
    source_type = Column(String, default="SITE_VISIT", nullable=False, index=True)
    project_scope = Column(String, default="SUPPLY_AND_INSTALL", nullable=False)
    verification_status = Column(String, default="UNVERIFIED", nullable=False, index=True)
    purpose = Column(String, nullable=True)
    scheduled_start = Column(DateTime, nullable=True)
    scheduled_end = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    client_approved_at = Column(DateTime, nullable=True)
    client_approved_by = Column(String, nullable=True)
    site_verified_at = Column(DateTime, nullable=True)
    site_verified_by = Column(String, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    client = relationship("Client", back_populates="measure_missions")
    site = relationship("ClientSiteAddress", back_populates="measure_missions")
    opportunity = relationship("CRMOpportunity", back_populates="measure_missions")
    sale_order = relationship("SaleOrder")
    assigned_user = relationship("User")
    dossiers = relationship(
        "MMG",
        back_populates="measure_mission",
        foreign_keys="MMG.measure_mission_id",
    )
    openings = relationship(
        "MeasureOpening",
        back_populates="mission",
        cascade="all, delete-orphan",
        order_by="MeasureOpening.sequence",
    )
    source_documents = relationship(
        "MeasureMissionDocument",
        back_populates="mission",
        cascade="all, delete-orphan",
        order_by="MeasureMissionDocument.uploaded_at",
    )
    technical_dossier = relationship(
        "TechnicalDossier",
        back_populates="mission",
        cascade="all, delete-orphan",
        uselist=False,
    )


class MeasureOpening(Base):
    __tablename__ = "measure_openings"
    __table_args__ = (
        UniqueConstraint("mission_id", "sequence", name="uq_measure_openings_mission_sequence"),
    )

    id = Column(Integer, primary_key=True, index=True)
    mission_id = Column(Integer, ForeignKey("measure_missions.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False, default=1)
    label = Column(String, nullable=False)
    room = Column(String, nullable=True)
    product_type = Column(String, default="WINDOW")
    width_mm = Column(Float, nullable=True)
    height_mm = Column(Float, nullable=True)
    passage_height_mm = Column(Float, nullable=True)
    material = Column(String, default="ALU")
    opening_type = Column(String, nullable=True)
    opening_side = Column(String, nullable=True)
    sash_count = Column(Integer, default=1)
    installation_type = Column(String, nullable=True)
    status = Column(String, default="DRAFT", nullable=False, index=True)
    configuration = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    mission = relationship("MeasureMission", back_populates="openings")
    documents = relationship(
        "MeasureMissionDocument",
        back_populates="opening",
        passive_deletes=True,
        order_by="MeasureMissionDocument.uploaded_at",
    )


class MeasureMissionDocument(Base):
    __tablename__ = "measure_mission_documents"

    id = Column(Integer, primary_key=True, index=True)
    mission_id = Column(
        Integer,
        ForeignKey("measure_missions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    opening_id = Column(
        Integer,
        ForeignKey("measure_openings.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    original_filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, default=0)
    document_type = Column(String, default="SOURCE_MEASURE")
    uploaded_by = Column(String, nullable=True)
    uploaded_at = Column(DateTime, default=utcnow)

    mission = relationship("MeasureMission", back_populates="source_documents")
    opening = relationship("MeasureOpening", back_populates="documents")


class TechnicalDossier(Base):
    __tablename__ = "technical_dossiers"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, nullable=False, index=True)
    mission_id = Column(
        Integer,
        ForeignKey("measure_missions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    quoting_status = Column(String, default="DRAFT", nullable=False, index=True)
    production_status = Column(String, default="LOCKED", nullable=False, index=True)
    external_source_system = Column(String, nullable=True, index=True)
    external_project_reference = Column(String, nullable=True, index=True)
    stock_status = Column(String, default="LOCKED", nullable=False, index=True)
    stock_review_note = Column(Text, nullable=True)
    stock_validated_at = Column(DateTime, nullable=True)
    stock_validated_by = Column(String, nullable=True)
    launch_status = Column(String, default="LOCKED", nullable=False, index=True)
    launch_review_note = Column(Text, nullable=True)
    launch_validated_at = Column(DateTime, nullable=True)
    launch_validated_by = Column(String, nullable=True)
    launched_at = Column(DateTime, nullable=True)
    launched_by = Column(String, nullable=True)
    quoting_review_note = Column(Text, nullable=True)
    production_review_note = Column(Text, nullable=True)
    quoting_submitted_at = Column(DateTime, nullable=True)
    quoting_submitted_by = Column(String, nullable=True)
    quoting_validated_at = Column(DateTime, nullable=True)
    quoting_validated_by = Column(String, nullable=True)
    production_submitted_at = Column(DateTime, nullable=True)
    production_submitted_by = Column(String, nullable=True)
    production_validated_at = Column(DateTime, nullable=True)
    production_validated_by = Column(String, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    mission = relationship("MeasureMission", back_populates="technical_dossier")
    versions = relationship(
        "TechnicalDossierVersion",
        back_populates="dossier",
        cascade="all, delete-orphan",
        order_by="TechnicalDossierVersion.version_number",
    )


class TechnicalDossierVersion(Base):
    __tablename__ = "technical_dossier_versions"
    __table_args__ = (
        UniqueConstraint(
            "dossier_id",
            "version_number",
            name="uq_technical_dossier_versions_number",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    dossier_id = Column(
        Integer,
        ForeignKey("technical_dossiers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number = Column(Integer, nullable=False)
    document_type = Column(String, nullable=False, default="QUOTING", index=True)
    source_system = Column(String, nullable=False, index=True)
    source_reference = Column(String, nullable=True)
    original_filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, default=0, nullable=False)
    checksum_sha256 = Column(String, nullable=False, index=True)
    opening_ids = Column(JSON, nullable=False, default=list)
    notes = Column(Text, nullable=True)
    analysis_status = Column(String, nullable=False, default="PENDING", index=True)
    detected_document_type = Column(String, nullable=True)
    detected_source_system = Column(String, nullable=True)
    detected_project_reference = Column(String, nullable=True, index=True)
    parsed_summary = Column(JSON, nullable=False, default=dict)
    parsed_records = Column(JSON, nullable=False, default=list)
    parsed_issues = Column(JSON, nullable=False, default=list)
    analyzed_at = Column(DateTime, nullable=True)
    stock_data_approved_at = Column(DateTime, nullable=True)
    stock_data_approved_by = Column(String, nullable=True)
    previous_version_id = Column(
        Integer,
        ForeignKey("technical_dossier_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    comparison_summary = Column(JSON, nullable=False, default=dict)
    impact_status = Column(String, nullable=False, default="INITIAL", index=True)
    revision_after_launch = Column(Boolean, nullable=False, default=False)
    revision_status = Column(String, nullable=False, default="NOT_REQUIRED", index=True)
    revision_review_note = Column(Text, nullable=True)
    revision_reviewed_at = Column(DateTime, nullable=True)
    revision_reviewed_by = Column(String, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    dossier = relationship("TechnicalDossier", back_populates="versions")
    previous_version = relationship(
        "TechnicalDossierVersion",
        remote_side=[id],
        foreign_keys=[previous_version_id],
    )

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
