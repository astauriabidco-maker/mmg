from pydantic import BaseModel, ConfigDict, Field
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
    job_title: Optional[str] = None
    team: Optional[str] = None
    access_mode: str = "PIN"
    role: str = "OPERATOR"
    additional_roles: List[str] = []
    stations: List['Station'] = [] # Changed to list of Station objects

class UserCreate(UserBase):
    pin: Optional[str] = None # 4 digits or temporary password
    station_codes: List[str] = [] # Codes of stations to associate
    send_invite: bool = False

class UserUpdate(BaseModel):
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None
    team: Optional[str] = None
    access_mode: Optional[str] = None
    role: Optional[str] = None
    additional_roles: Optional[List[str]] = None
    pin: Optional[str] = None # Optional PIN reset
    station_codes: Optional[List[str]] = None

class User(UserBase):
    id: int
    is_active: bool
    invitation_status: Optional[str] = None
    invited_at: Optional[datetime] = None
    pin_must_change: bool = False
    last_login_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

class UserCreateResponse(BaseModel):
    user: User
    temporary_pin: Optional[str] = None
    invitation_sent: bool = False
    invitation_link: Optional[str] = None
    message: str

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
    country: Optional[str] = None
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
    country: Optional[str] = None
    tax_id: Optional[str] = None
    supplier_status: str = "ACTIVE"
    supplier_category: Optional[str] = None
    default_currency: str = "EUR"
    incoterm: Optional[str] = None
    delivery_terms: Optional[str] = None
    website: Optional[str] = None
    payment_terms: Optional[str] = None
    lead_time_days: Optional[int] = None
    preferred_contact_method: Optional[str] = None
    notes: Optional[str] = None
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
    # Options fines (plus-values du devis)
    ventilation: Optional[str] = "Aucune" # Aucune / Standard / Acoustique
    shape: Optional[str] = "Rectangulaire" # Rectangulaire / Cintré / Trapèze / Triangle
    soubassement_type: Optional[str] = "Vitré" # Vitré / Plein

class MMGAnnexes(BaseModel):
    volet_roulant: Optional[str] = "Aucun" # Aucun / Manuel / Electrique / Solaire
    volet_battant: Optional[str] = "Aucun" # Aucun / 1 Vantail / 2 Vantaux
    moustiquaire: bool = False
    frais_pose: Optional[str] = "Aucun" # Aucun / Standard / Renovation / Complexe
    livraison: bool = False

class MMGLogistics(BaseModel):
    floor_number: int = 0
    access_difficulty: Optional[str] = "Standard"
    environment: Optional[str] = "Standard"

class ClientSiteAddressBase(BaseModel):
    label: str = "Chantier"
    address_line1: str
    address_line2: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: str = "FR"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    access_instructions: Optional[str] = None
    is_default: bool = False

class ClientSiteAddressCreate(ClientSiteAddressBase):
    client_id: Optional[int] = None

class ClientSiteAddressResponse(ClientSiteAddressBase):
    id: int
    reference: str
    client_id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


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


class CRMOpportunityCreate(BaseModel):
    client_id: int
    site_address_id: Optional[int] = None
    owner_user_id: Optional[int] = None
    sale_order_id: Optional[int] = None
    title: str = Field(min_length=1, max_length=255)
    origin: Optional[str] = Field(default=None, max_length=100)
    need_type: CRMNeedType = CRMNeedType.OTHER
    stage: CRMOpportunityStage = CRMOpportunityStage.NEW
    estimated_amount: Optional[float] = Field(default=None, ge=0)
    probability: int = Field(default=10, ge=0, le=100)
    next_milestone: Optional[str] = Field(default=None, max_length=255)
    next_milestone_at: Optional[datetime] = None
    expected_close_date: Optional[datetime] = None
    loss_reason: Optional[str] = None


class CRMOpportunityUpdate(BaseModel):
    site_address_id: Optional[int] = None
    owner_user_id: Optional[int] = None
    sale_order_id: Optional[int] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    origin: Optional[str] = Field(default=None, max_length=100)
    need_type: Optional[CRMNeedType] = None
    stage: Optional[CRMOpportunityStage] = None
    estimated_amount: Optional[float] = Field(default=None, ge=0)
    probability: Optional[int] = Field(default=None, ge=0, le=100)
    next_milestone: Optional[str] = Field(default=None, max_length=255)
    next_milestone_at: Optional[datetime] = None
    expected_close_date: Optional[datetime] = None
    loss_reason: Optional[str] = None


class CRMOpportunityResponse(BaseModel):
    id: int
    reference: str
    client_id: int
    client_name: Optional[str] = None
    site_address_id: Optional[int] = None
    site_reference: Optional[str] = None
    owner_user_id: Optional[int] = None
    owner_name: Optional[str] = None
    sale_order_id: Optional[int] = None
    title: str
    origin: Optional[str] = None
    need_type: CRMNeedType
    stage: CRMOpportunityStage
    estimated_amount: Optional[float] = None
    probability: int
    next_milestone: Optional[str] = None
    next_milestone_at: Optional[datetime] = None
    expected_close_date: Optional[datetime] = None
    loss_reason: Optional[str] = None
    stage_entered_at: datetime
    won_at: Optional[datetime] = None
    lost_at: Optional[datetime] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CRMActivityCreate(BaseModel):
    client_id: int
    opportunity_id: Optional[int] = None
    activity_type: CRMActivityType
    subject: str = Field(min_length=1, max_length=255)
    note: Optional[str] = None
    due_at: Optional[datetime] = None
    status: CRMActivityStatus = CRMActivityStatus.TODO


class CRMCockpitAssignOwnerRequest(BaseModel):
    owner_user_id: int


class CRMCockpitScheduleActionRequest(BaseModel):
    activity_type: CRMActivityType = CRMActivityType.TASK
    subject: str = Field(min_length=1, max_length=255)
    note: Optional[str] = None
    due_at: datetime
    reminder_plan_id: Optional[int] = None


class CRMActivityUpdate(BaseModel):
    opportunity_id: Optional[int] = None
    activity_type: Optional[CRMActivityType] = None
    subject: Optional[str] = Field(default=None, min_length=1, max_length=255)
    note: Optional[str] = None
    due_at: Optional[datetime] = None
    status: Optional[CRMActivityStatus] = None


class CRMActivityResponse(BaseModel):
    id: int
    client_id: int
    client_name: Optional[str] = None
    opportunity_id: Optional[int] = None
    opportunity_reference: Optional[str] = None
    activity_type: CRMActivityType
    subject: str
    note: Optional[str] = None
    due_at: Optional[datetime] = None
    status: CRMActivityStatus
    author: str
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CRMCockpitMetrics(BaseModel):
    open_opportunities: int
    pipeline_amount: float
    weighted_pipeline_amount: float
    overdue_actions: int
    reminders_today: int = 0
    overdue_reminders: int = 0
    opportunities_without_action: int = 0
    measures_to_schedule: int
    automatic_reminders: int


class CRMCockpitStage(BaseModel):
    stage: CRMOpportunityStage
    count: int
    amount: float
    weighted_amount: float


class CRMCockpitAgendaItem(BaseModel):
    kind: str
    id: int
    client_id: int
    client_name: str
    opportunity_id: Optional[int] = None
    reference: Optional[str] = None
    title: str
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    status: str
    owner_name: Optional[str] = None
    overdue: bool = False


class CRMCockpitReminder(BaseModel):
    key: str
    kind: str
    severity: str
    client_id: int
    client_name: str
    client_email: Optional[str] = None
    target_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    reference: Optional[str] = None
    title: str
    reason: str
    suggested_subject: str
    due_at: Optional[datetime] = None
    existing_activity_id: Optional[int] = None


class CRMCockpitOpportunitySummary(BaseModel):
    id: int
    reference: str
    client_id: int
    client_name: str
    client_email: Optional[str] = None
    title: str
    stage: CRMOpportunityStage
    owner_user_id: Optional[int] = None
    owner_name: Optional[str] = None
    amount: float = 0
    updated_at: Optional[datetime] = None


class CRMCockpitOwnerPerformance(BaseModel):
    owner_user_id: Optional[int] = None
    owner_name: str
    open_opportunities: int = 0
    pipeline_amount: float = 0
    reminders_today: int = 0
    overdue_reminders: int = 0
    opportunities_without_action: int = 0


class CRMCockpitStageConversion(BaseModel):
    stage: CRMOpportunityStage
    entered_count: int = 0
    advanced_count: int = 0
    lost_count: int = 0
    decided_count: int = 0
    conversion_rate: Optional[float] = None


class CRMCockpitResponse(BaseModel):
    generated_at: datetime
    horizon_days: int
    metrics: CRMCockpitMetrics
    stages: List[CRMCockpitStage]
    agenda: List[CRMCockpitAgendaItem]
    reminders: List[CRMCockpitReminder]
    reminders_today: List[CRMCockpitReminder] = Field(default_factory=list)
    overdue_reminders: List[CRMCockpitReminder] = Field(default_factory=list)
    opportunities_without_action: List[CRMCockpitOpportunitySummary] = Field(default_factory=list)
    owners: List[CRMCockpitOwnerPerformance] = Field(default_factory=list)
    stage_conversions: List[CRMCockpitStageConversion] = Field(default_factory=list)


class CRMReminderTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    description: Optional[str] = None
    subject_template: Optional[str] = Field(default=None, min_length=1, max_length=255)
    body_template: Optional[str] = Field(default=None, min_length=1)
    is_active: Optional[bool] = None


class CRMReminderTemplateResponse(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    subject_template: str
    body_template: str
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CRMReminderRuleUpdate(BaseModel):
    delay_days: Optional[int] = Field(default=None, ge=0, le=90)
    template_id: Optional[int] = None
    assignment_strategy: Optional[str] = Field(default=None, pattern="^(OPPORTUNITY_OWNER|FIXED_USER)$")
    fixed_user_id: Optional[int] = None
    is_active: Optional[bool] = None


class CRMReminderRuleResponse(BaseModel):
    id: int
    name: str
    stage: CRMOpportunityStage
    delay_days: int
    template_id: Optional[int] = None
    template_name: Optional[str] = None
    assignment_strategy: str
    fixed_user_id: Optional[int] = None
    fixed_user_name: Optional[str] = None
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CRMReminderPlanResponse(BaseModel):
    id: int
    plan_key: str
    rule_id: int
    rule_name: Optional[str] = None
    client_id: int
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    opportunity_id: int
    opportunity_reference: Optional[str] = None
    opportunity_title: Optional[str] = None
    assigned_user_id: Optional[int] = None
    assigned_user_name: Optional[str] = None
    template_id: Optional[int] = None
    stage_snapshot: CRMOpportunityStage
    due_at: datetime
    status: str
    cancelled_reason: Optional[str] = None
    sent_delivery_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CRMReminderPlanCancel(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class CRMReminderSyncResponse(BaseModel):
    created: int
    cancelled: int


class CRMReminderPreviewRequest(BaseModel):
    plan_id: Optional[int] = None
    client_id: int
    opportunity_id: Optional[int] = None
    template_id: Optional[int] = None
    reminder_kind: Optional[str] = None
    due_at: Optional[datetime] = None


class CRMReminderPreviewResponse(BaseModel):
    plan_id: Optional[int] = None
    template_id: int
    template_code: str
    template_name: str
    recipient: str
    subject: str
    message: str
    smtp_configured: bool


class CRMReminderSendRequest(BaseModel):
    plan_id: Optional[int] = None
    reminder_key: Optional[str] = Field(default=None, max_length=255)
    client_id: int
    opportunity_id: Optional[int] = None
    template_id: Optional[int] = None
    recipient: str = Field(min_length=3, max_length=320)
    subject: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1)
    confirm_send: bool = False


class CRMReminderDeliveryResponse(BaseModel):
    id: int
    reminder_key: Optional[str] = None
    client_id: int
    client_name: Optional[str] = None
    opportunity_id: Optional[int] = None
    opportunity_reference: Optional[str] = None
    template_id: Optional[int] = None
    template_name: Optional[str] = None
    activity_id: Optional[int] = None
    recipient: str
    subject: str
    message: str
    status: str
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_by: str
    created_at: datetime
    notification: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


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

class MeasureSourceType(str, enum.Enum):
    SITE_VISIT = "SITE_VISIT"
    CLIENT_DOCUMENTS = "CLIENT_DOCUMENTS"
    AGENCY_ASSISTED = "AGENCY_ASSISTED"

class MeasureProjectScope(str, enum.Enum):
    SUPPLY_ONLY = "SUPPLY_ONLY"
    SUPPLY_AND_INSTALL = "SUPPLY_AND_INSTALL"

class MeasureVerificationStatus(str, enum.Enum):
    UNVERIFIED = "UNVERIFIED"
    BE_REVIEWED = "BE_REVIEWED"
    CLIENT_APPROVAL_REQUIRED = "CLIENT_APPROVAL_REQUIRED"
    SITE_VERIFICATION_REQUIRED = "SITE_VERIFICATION_REQUIRED"
    READY_FOR_FABRICATION = "READY_FOR_FABRICATION"

class MeasureMissionCreate(BaseModel):
    client_id: int
    site_address_id: Optional[int] = None
    site: Optional[ClientSiteAddressCreate] = None
    opportunity_id: Optional[int] = None
    sale_order_id: Optional[int] = None
    assigned_user_id: Optional[int] = None
    source_type: MeasureSourceType = MeasureSourceType.SITE_VISIT
    project_scope: Optional[MeasureProjectScope] = None
    purpose: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    notes: Optional[str] = None
    status: MeasureMissionStatus = MeasureMissionStatus.DRAFT

class MeasureMissionUpdate(BaseModel):
    site_address_id: Optional[int] = None
    site: Optional[ClientSiteAddressCreate] = None
    opportunity_id: Optional[int] = None
    assigned_user_id: Optional[int] = None
    project_scope: Optional[MeasureProjectScope] = None
    purpose: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    notes: Optional[str] = None

class MeasureMissionStatusUpdate(BaseModel):
    status: MeasureMissionStatus

class MeasureVerificationAction(str, enum.Enum):
    CLIENT_APPROVED = "CLIENT_APPROVED"
    SITE_VERIFIED = "SITE_VERIFIED"

class MeasureVerificationUpdate(BaseModel):
    action: MeasureVerificationAction

class MeasureMissionDocumentResponse(BaseModel):
    id: int
    mission_id: int
    opening_id: Optional[int] = None
    original_filename: str
    content_type: Optional[str] = None
    file_size: int = 0
    document_type: str
    uploaded_by: Optional[str] = None
    uploaded_at: datetime
    model_config = ConfigDict(from_attributes=True)

class TechnicalDossierStatus(str, enum.Enum):
    LOCKED = "LOCKED"
    DRAFT = "DRAFT"
    TO_REVIEW = "TO_REVIEW"
    CORRECTION_REQUIRED = "CORRECTION_REQUIRED"
    VALIDATED = "VALIDATED"
    ARCHIVED = "ARCHIVED"

class TechnicalDocumentType(str, enum.Enum):
    QUOTING = "QUOTING"
    FABRICATION = "FABRICATION"
    CUTTING = "CUTTING"
    VALUATION = "VALUATION"

class TechnicalSourceSystem(str, enum.Enum):
    PROGES = "PROGES"
    ORGADATA = "ORGADATA"
    INTERNAL = "INTERNAL"
    OTHER = "OTHER"

class TechnicalDossierVersionResponse(BaseModel):
    id: int
    dossier_id: int
    version_number: int
    document_type: TechnicalDocumentType
    source_system: TechnicalSourceSystem
    source_reference: Optional[str] = None
    original_filename: str
    content_type: Optional[str] = None
    file_size: int = 0
    checksum_sha256: str
    opening_ids: List[int] = Field(default_factory=list)
    notes: Optional[str] = None
    analysis_status: str = "PENDING"
    detected_document_type: Optional[str] = None
    detected_source_system: Optional[str] = None
    detected_project_reference: Optional[str] = None
    parsed_summary: dict = Field(default_factory=dict)
    parsed_records: List[dict] = Field(default_factory=list)
    parsed_issues: List[dict] = Field(default_factory=list)
    analyzed_at: Optional[datetime] = None
    stock_data_approved_at: Optional[datetime] = None
    stock_data_approved_by: Optional[str] = None
    previous_version_id: Optional[int] = None
    comparison_summary: dict = Field(default_factory=dict)
    impact_status: str = "INITIAL"
    revision_after_launch: bool = False
    revision_status: str = "NOT_REQUIRED"
    revision_review_note: Optional[str] = None
    revision_reviewed_at: Optional[datetime] = None
    revision_reviewed_by: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class TechnicalDossierResponse(BaseModel):
    id: int
    reference: str
    mission_id: int
    quoting_status: TechnicalDossierStatus
    production_status: TechnicalDossierStatus
    external_source_system: Optional[str] = None
    external_project_reference: Optional[str] = None
    stock_status: TechnicalDossierStatus = TechnicalDossierStatus.LOCKED
    stock_review_note: Optional[str] = None
    stock_validated_at: Optional[datetime] = None
    stock_validated_by: Optional[str] = None
    launch_status: TechnicalDossierStatus = TechnicalDossierStatus.LOCKED
    launch_review_note: Optional[str] = None
    launch_validated_at: Optional[datetime] = None
    launch_validated_by: Optional[str] = None
    launched_at: Optional[datetime] = None
    launched_by: Optional[str] = None
    quoting_review_note: Optional[str] = None
    production_review_note: Optional[str] = None
    quoting_submitted_at: Optional[datetime] = None
    quoting_submitted_by: Optional[str] = None
    quoting_validated_at: Optional[datetime] = None
    quoting_validated_by: Optional[str] = None
    production_submitted_at: Optional[datetime] = None
    production_submitted_by: Optional[str] = None
    production_validated_at: Optional[datetime] = None
    production_validated_by: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    versions: List[TechnicalDossierVersionResponse] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)

class TechnicalDossierReviewAction(str, enum.Enum):
    VALIDATE = "VALIDATE"
    REQUEST_CORRECTION = "REQUEST_CORRECTION"

class TechnicalDossierReviewRequest(BaseModel):
    phase: TechnicalDocumentType
    action: TechnicalDossierReviewAction
    note: Optional[str] = None


class TechnicalGate(str, enum.Enum):
    STOCK = "STOCK"
    LAUNCH = "LAUNCH"


class TechnicalGateReviewRequest(BaseModel):
    gate: TechnicalGate
    action: TechnicalDossierReviewAction
    note: Optional[str] = None


class TechnicalRevisionReviewRequest(BaseModel):
    action: TechnicalDossierReviewAction
    note: Optional[str] = None

class MeasureOpeningStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    COMPLETE = "COMPLETE"
    TO_REVIEW = "TO_REVIEW"
    CORRECTION_REQUIRED = "CORRECTION_REQUIRED"
    VALIDATED = "VALIDATED"

class MeasureOpeningBase(BaseModel):
    label: str
    room: Optional[str] = None
    product_type: str = "WINDOW"
    width_mm: Optional[float] = None
    height_mm: Optional[float] = None
    passage_height_mm: Optional[float] = None
    material: str = "ALU"
    opening_type: Optional[str] = None
    opening_side: Optional[str] = None
    sash_count: int = 1
    installation_type: Optional[str] = None
    status: MeasureOpeningStatus = MeasureOpeningStatus.DRAFT
    configuration: Optional[dict] = None
    notes: Optional[str] = None

class MeasureOpeningCreate(MeasureOpeningBase):
    sequence: Optional[int] = None

class MeasureOpeningUpdate(BaseModel):
    label: Optional[str] = None
    room: Optional[str] = None
    product_type: Optional[str] = None
    width_mm: Optional[float] = None
    height_mm: Optional[float] = None
    passage_height_mm: Optional[float] = None
    material: Optional[str] = None
    opening_type: Optional[str] = None
    opening_side: Optional[str] = None
    sash_count: Optional[int] = None
    installation_type: Optional[str] = None
    status: Optional[MeasureOpeningStatus] = None
    configuration: Optional[dict] = None
    notes: Optional[str] = None

class MeasureOpeningResponse(MeasureOpeningBase):
    id: int
    mission_id: int
    sequence: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class MeasureMissionResponse(BaseModel):
    id: int
    reference: str
    client_id: int
    client_name: str
    site_address_id: Optional[int] = None
    site: Optional[ClientSiteAddressResponse] = None
    opportunity_id: Optional[int] = None
    sale_order_id: Optional[int] = None
    sale_order_status: Optional[str] = None
    assigned_user_id: Optional[int] = None
    assigned_user_name: Optional[str] = None
    status: MeasureMissionStatus
    source_type: MeasureSourceType
    project_scope: MeasureProjectScope
    verification_status: MeasureVerificationStatus
    purpose: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    notes: Optional[str] = None
    client_approved_at: Optional[datetime] = None
    client_approved_by: Optional[str] = None
    site_verified_at: Optional[datetime] = None
    site_verified_by: Optional[str] = None
    dossier_ids: List[int] = Field(default_factory=list)
    openings: List[MeasureOpeningResponse] = Field(default_factory=list)
    source_documents: List[MeasureMissionDocumentResponse] = Field(default_factory=list)
    technical_dossier: Optional[TechnicalDossierResponse] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class MeasureMissionQuoteResponse(BaseModel):
    mission_id: int
    sale_order_id: int
    sale_reference: str
    created: bool
    line_count: int

class MMGCreate(BaseModel):
    client: MMGClient
    client_id: Optional[int] = None
    site_address_id: Optional[int] = None
    site: Optional[ClientSiteAddressCreate] = None
    measure_mission_id: Optional[int] = None
    measurements: MMGMeasurements
    options: MMGOptions
    configuration: MMGConfiguration
    annexes: Optional[MMGAnnexes] = None
    logistics: Optional[MMGLogistics] = None
    sale_order_id: Optional[int] = None
    photos: List[str]
    signature: str # Base64

class MMGResponse(BaseModel):
    id: int
    reference: str
    client_name: str
    client_id: Optional[int] = None
    site_address_id: Optional[int] = None
    measure_mission_id: Optional[int] = None
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
    # Configuration fine persistée (forme, ventilation, soubassement, annexes...)
    configuration: Optional[dict] = None
    
    model_config = ConfigDict(from_attributes=True)

# --- STOCK V3 PIM ---
from typing import List

class ProductVariantBase(BaseModel):
    reference: str
    barcode: Optional[str] = None
    color: Optional[str] = None
    finish: Optional[str] = None
    length_per_unit: Optional[float] = None
    conditioning: Optional[str] = None
    units_per_package: Optional[float] = None
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
    category: Optional[str] = None
    material_type: str
    unit: str
    supplier: Optional[str] = None
    product_type: str = "stockable"
    available_in_pos: bool = False
    image_url: Optional[str] = None
    technical_doc_url: Optional[str] = None
    compatible_series: Optional[str] = None
    # Compatibilité API historique : les intégrations existantes créent un
    # article actif si elles ne transmettent pas de statut. L'UI gouvernée
    # transmet explicitement DRAFT pour toute nouvelle fiche.
    catalog_status: str = "ACTIVE"

class ProductCreate(ProductBase):
    variants: List[ProductVariantCreate] = []

class ProductResponse(ProductBase):
    id: int
    variants: List[ProductVariantResponse] = []
    model_config = ConfigDict(from_attributes=True)


class ProductStatusUpdate(BaseModel):
    status: str
    reason: Optional[str] = None


class ProductAuditLogResponse(BaseModel):
    id: int
    product_id: int
    variant_id: Optional[int] = None
    action: str
    changes: Optional[dict] = None
    reason: Optional[str] = None
    author: str
    created_at: datetime
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
    # Renseignés uniquement sur les emplacements internes : réservé ferme et
    # disponible calculés PAR EMPLACEMENT (None ailleurs).
    reserved_quantity: Optional[float] = None
    available_quantity: Optional[float] = None
    model_config = ConfigDict(from_attributes=True)

class StockMoveCreate(BaseModel):
    variant_id: int
    location_id: Optional[int] = None # Source
    location_dest_id: Optional[int] = None # Dest
    quantity: float
    notes: Optional[str] = None
    reason: Optional[str] = None
    source_screen: Optional[str] = None
    document_type: Optional[str] = None
    document_reference: Optional[str] = None

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
    source_screen: Optional[str] = None
    document_type: Optional[str] = None
    document_reference: Optional[str] = None
    business_reason: Optional[str] = None
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
    location_id: Optional[int] = None
    status: str
    notes: Optional[str] = None
    created_by: str
    created_at: datetime
    consumed_at: Optional[datetime] = None
    lines: List[StockReservationLineResponse] = []
    model_config = ConfigDict(from_attributes=True)


class WorkshopPreparationCreate(BaseModel):
    reservation_id: int
    destination_location_id: Optional[int] = None
    notes: Optional[str] = None


class WorkshopPreparationLineUpdate(BaseModel):
    prepared_quantity: float


class WorkshopPreparationLineResponse(BaseModel):
    id: int
    reservation_line_id: int
    variant_id: int
    planned_quantity: float
    prepared_quantity: float
    transferred_quantity: float
    returned_quantity: float
    status: str
    variant: Optional[ProductVariantResponse] = None
    model_config = ConfigDict(from_attributes=True)


class WorkshopPreparationResponse(BaseModel):
    id: int
    reference: str
    reservation_id: int
    sale_order_id: Optional[int] = None
    production_order_id: Optional[int] = None
    source_location_id: int
    destination_location_id: int
    status: str
    notes: Optional[str] = None
    created_by: str
    created_at: datetime
    handed_over_by: Optional[str] = None
    handed_over_at: Optional[datetime] = None
    returned_by: Optional[str] = None
    returned_at: Optional[datetime] = None
    source_location: Optional[StockLocationResponse] = None
    destination_location: Optional[StockLocationResponse] = None
    lines: List[WorkshopPreparationLineResponse] = []
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
    # Gel de zone imposé à True par défaut côté serveur. Le client peut
    # explicitement demander False (comptage sans gel) ; la garde anti-dérive
    # 409 à la validation reste alors le filet de sécurité.
    zone_locked: Optional[bool] = None
    # Pré-remplit aussi les variantes actives sans stock dans la zone (espéré 0)
    # pour détecter les oublis de comptage.
    include_all_variants: bool = False
    # Comptage aveugle : l'API masque expected_quantity/variance des lignes
    # jusqu'à la validation (les écarts restent calculés côté serveur).
    blind_counting: bool = False

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
    # Null en comptage aveugle (espéré/écart masqués jusqu'à validation).
    expected_quantity: Optional[float] = None
    counted_quantity: Optional[float] = None
    variance_quantity: Optional[float] = None
    status: str = "ok"
    reason: Optional[str] = None
    notes: Optional[str] = None
    recount_requested_by: Optional[str] = None
    recount_requested_at: Optional[datetime] = None
    recount_notes: Optional[str] = None
    counted_by: Optional[str] = None
    counted_at: Optional[datetime] = None
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
    blind_counting: bool = False
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
    signature_path: Optional[str] = None
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
    previous_seal: Optional[str] = None
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

class DeliveryConfirmRequest(BaseModel):
    """Confirmation de livraison : signature client en base64 (data URL acceptée)."""
    signature_image: Optional[str] = None

class DeliveryNoteResponse(DeliveryNoteBase):
    id: int
    reference: str
    route_id: Optional[int] = None
    signed_at: Optional[datetime] = None
    signature_path: Optional[str] = None
    
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
