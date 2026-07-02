from sqlalchemy import Column, Integer, String, Enum as SAEnum, DateTime, ForeignKey, Float, Boolean, Text, inspect, text
from sqlalchemy.orm import relationship
from .database import Base
import enum
from datetime import datetime


def ensure_schema_compatibility(engine):
    """Patch legacy SQLite schemas that predate the Alembic drift fixes."""
    with engine.begin() as connection:
        inspector = inspect(connection)

        if inspector.has_table("products"):
            product_columns = {column["name"] for column in inspector.get_columns("products")}
            if "technical_doc_url" not in product_columns:
                connection.execute(text("ALTER TABLE products ADD COLUMN technical_doc_url VARCHAR"))
            if "compatible_series" not in product_columns:
                connection.execute(text("ALTER TABLE products ADD COLUMN compatible_series VARCHAR"))
            if "catalog_status" not in product_columns:
                connection.execute(text("ALTER TABLE products ADD COLUMN catalog_status VARCHAR DEFAULT 'ACTIVE'"))
                product_columns.add("catalog_status")
            connection.execute(text("UPDATE products SET catalog_status = 'ACTIVE' WHERE catalog_status IS NULL"))

        if inspector.has_table("delivery_notes"):
            delivery_columns = {column["name"] for column in inspector.get_columns("delivery_notes")}
            if "sale_order_id" not in delivery_columns:
                connection.execute(text("ALTER TABLE delivery_notes ADD COLUMN sale_order_id INTEGER"))
                delivery_columns.add("sale_order_id")
            if "delivery_notes" not in delivery_columns:
                connection.execute(text("ALTER TABLE delivery_notes ADD COLUMN delivery_notes TEXT"))
                delivery_columns.add("delivery_notes")
            if "notes" in delivery_columns:
                connection.execute(
                    text(
                        "UPDATE delivery_notes "
                        "SET delivery_notes = notes "
                        "WHERE delivery_notes IS NULL AND notes IS NOT NULL"
                    )
                )

        if inspector.has_table("orders"):
            order_columns = {column["name"] for column in inspector.get_columns("orders")}
            if "sale_order_id" not in order_columns:
                connection.execute(text("ALTER TABLE orders ADD COLUMN sale_order_id INTEGER"))
            if "sale_order_line_id" not in order_columns:
                connection.execute(text("ALTER TABLE orders ADD COLUMN sale_order_line_id INTEGER"))

        if inspector.has_table("sale_orders"):
            sale_columns = {column["name"] for column in inspector.get_columns("sale_orders")}
            if "workflow_type" not in sale_columns:
                connection.execute(text("ALTER TABLE sale_orders ADD COLUMN workflow_type VARCHAR DEFAULT 'FREE_SALE'"))
                sale_columns.add("workflow_type")
            connection.execute(text("UPDATE sale_orders SET workflow_type = 'FREE_SALE' WHERE workflow_type IS NULL"))

        if inspector.has_table("sale_order_lines"):
            sale_line_columns = {column["name"] for column in inspector.get_columns("sale_order_lines")}
            if "line_type" not in sale_line_columns:
                connection.execute(text("ALTER TABLE sale_order_lines ADD COLUMN line_type VARCHAR DEFAULT 'SERVICE'"))
                sale_line_columns.add("line_type")
            connection.execute(
                text(
                    "UPDATE sale_order_lines "
                    "SET line_type = CASE WHEN variant_id IS NOT NULL THEN 'STOCK_ITEM' ELSE 'SERVICE' END "
                    "WHERE line_type IS NULL OR line_type = ''"
                )
            )

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
    pin_hash = Column(String) # Hashed 4-digit PIN
    role = Column(String, default="OPERATOR") # Link to roles.name
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
    assigned_to = Column(String, nullable=True) # Name of the operator
    created_at = Column(DateTime, default=datetime.utcnow)

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
    cost_price = Column(Float, nullable=True)
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
    date = Column(DateTime, default=datetime.utcnow)
    variant_id = Column(Integer, ForeignKey("product_variants.id"))
    location_id = Column(Integer, ForeignKey("stock_locations.id"), nullable=True) # Source
    location_dest_id = Column(Integer, ForeignKey("stock_locations.id"), nullable=True) # Dest
    quantity = Column(Float)
    state = Column(String, default="done")
    notes = Column(String, nullable=True)
    author = Column(String, default="Système")

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
    status = Column(String, default="reserved", index=True) # reserved, consumed, cancelled
    notes = Column(Text, nullable=True)
    created_by = Column(String, default="Système")
    created_at = Column(DateTime, default=datetime.utcnow)
    consumed_at = Column(DateTime, nullable=True)

    lines = relationship("StockReservationLine", back_populates="reservation", cascade="all, delete-orphan")
    sale_order = relationship("SaleOrder")
    production_order = relationship("Order")

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
    sale_order_id = Column(Integer, ForeignKey("sale_orders.id"), nullable=True)
    
    status = Column(SAEnum(MMGStatus), default=MMGStatus.SENT)
    
    sale_order = relationship("SaleOrder", back_populates="mmg_dossiers")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
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
    created_at = Column(DateTime, default=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
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
    unit_price = Column(Float, default=0.0) # HT
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
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    starting_cash = Column(Float, default=0.0)
    closing_cash = Column(Float, nullable=True)
    status = Column(String, default="OPEN") # OPEN, CLOSED
    
    orders = relationship("POSOrder", back_populates="session", cascade="all, delete-orphan")
    cash_movements = relationship("POSCashMovement", back_populates="session", cascade="all, delete-orphan")

class POSCashMovement(Base):
    __tablename__ = "pos_cash_movements"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("pos_sessions.id"))
    movement_type = Column(String) # IN, OUT
    amount = Column(Float, default=0.0)
    reason = Column(String)
    author = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    session = relationship("POSSession", back_populates="cash_movements")

class POSOrder(Base):
    __tablename__ = "pos_orders"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("pos_sessions.id"))
    reference = Column(String, unique=True, index=True) # TK-2026-00001
    date = Column(DateTime, default=datetime.utcnow)
    payment_method = Column(String, default="CASH") # CASH, CB, MOBO
    tax_rate = Column(Float, default=18.0)
    currency = Column(String, default="EUR")
    amount_total = Column(Float, default=0.0)
    amount_paid = Column(Float, default=0.0)
    amount_return = Column(Float, default=0.0)
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
    unit_price = Column(Float, default=0.0) # HT
    
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
    created_at = Column(DateTime, default=datetime.utcnow)

# --- FOURNISSEURS (SUPPLIERS) ---
class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    contact_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    tax_id = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# --- ACHATS (PURCHASES) ---
class PurchaseOrderStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    PARTIAL = "PARTIAL"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True) # Ex: PO-2026-0001
    supplier = Column(String)
    order_date = Column(DateTime, default=datetime.utcnow)
    expected_date = Column(DateTime, nullable=True)
    status = Column(SAEnum(PurchaseOrderStatus), default=PurchaseOrderStatus.DRAFT)
    total_amount = Column(Float, default=0.0)
    notes = Column(Text, nullable=True)
    author = Column(String, default="Système")
    
    lines = relationship("PurchaseOrderLine", back_populates="order", cascade="all, delete-orphan")

class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("purchase_orders.id"))
    variant_id = Column(Integer, ForeignKey("product_variants.id"))
    quantity = Column(Float, default=1.0)
    quantity_received = Column(Float, default=0.0)
    unit_price = Column(Float, default=0.0)
    
    order = relationship("PurchaseOrder", back_populates="lines")
    variant = relationship("ProductVariant")

# --- FACTURATION (FRANCE NF525) ---

class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True) # F-YYYY-XXXX
    sale_order_id = Column(Integer, ForeignKey("sale_orders.id"), nullable=True)
    client_name = Column(String)
    client_address = Column(String, nullable=True)
    client_siret = Column(String, nullable=True) # France Specific
    issue_date = Column(DateTime, default=datetime.utcnow)
    due_date = Column(DateTime)
    status = Column(String, default="DRAFT") # DRAFT, UNPAID, PARTIAL, PAID, AVOIR
    
    subtotal = Column(Float, default=0.0)
    tax_rate = Column(Float, default=20.0) # French standard TVA
    tax_amount = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    
    qr_code_hash = Column(String, nullable=True) # Anti-fraude seal
    
    lines = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")
    sale_order = relationship("SaleOrder")

class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    description = Column(String)
    quantity = Column(Float, default=1.0)
    unit_price = Column(Float)
    tax_rate = Column(Float, default=20.0)
    
    invoice = relationship("Invoice", back_populates="lines")

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    amount = Column(Float)
    payment_date = Column(DateTime, default=datetime.utcnow)
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
