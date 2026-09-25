"""Ontologie métier MMG.

Ce module centralise le vocabulaire canonique entre CRM, bureau d'études,
devis, commande, fabrication, stock et débit atelier. Il est volontairement
sans dépendance base de données pour rester exploitable par les tests, l'API,
la documentation et de futurs usages IA/RAG.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


MMG_MODULES = (
    "CRM",
    "BE",
    "DEVIS",
    "COMMANDE",
    "FABRICATION",
    "STOCK",
    "ACHATS",
    "DEBIT",
)

TechnicalDocumentKind = Literal["QUOTING", "VALUATION", "FABRICATION", "CUTTING"]
TechnicalSourceSystem = Literal["PROGES", "ORGADATA", "INTERNAL", "OTHER"]


DOCUMENT_TYPES: dict[TechnicalDocumentKind, dict[str, object]] = {
    "QUOTING": {
        "label": "Chiffrage technique",
        "stock_source": False,
    },
    "VALUATION": {
        "label": "Valorisation",
        "stock_source": False,
    },
    "FABRICATION": {
        "label": "Fiche fabrication",
        "stock_source": False,
    },
    "CUTTING": {
        "label": "Fiche de débit",
        "stock_source": True,
    },
}


@dataclass(frozen=True)
class Entity:
    id: str
    label: str
    module: str
    definition: str
    source_models: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    required_before: tuple[str, ...] = ()

    @property
    def code(self) -> str:
        """Nom court historique utilisé par certains tests/outils."""

        return self.id


@dataclass(frozen=True)
class Relation:
    source: str
    relation: str
    target: str
    required: bool = False
    rule: str | None = None


@dataclass(frozen=True)
class ExternalDocumentMapping:
    source_system: TechnicalSourceSystem
    document_type: TechnicalDocumentKind
    canonical_entity: str
    label: str
    definition: str
    forbidden_confusions: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowGate:
    id: str
    label: str
    from_entity: str
    to_entity: str
    required_entities: tuple[str, ...]
    rule: str


@dataclass(frozen=True)
class EntityStatus:
    entity: str
    code: str
    label: str
    final: bool = False


@dataclass(frozen=True)
class BusinessEvent:
    code: str
    label: str
    source_entity: str
    target_entity: str | None
    description: str


@dataclass(frozen=True)
class StepPermission:
    entity: str
    action: str
    permission: str
    description: str


ENTITIES: dict[str, Entity] = {
    "client": Entity(
        id="client",
        label="Client",
        module="CRM",
        definition="Personne morale ou physique à l'origine d'un projet MMG.",
        source_models=("Client",),
    ),
    "contact": Entity(
        id="contact",
        label="Contact client",
        module="CRM",
        definition="Interlocuteur opérationnel ou décisionnaire rattaché au client.",
        source_models=("ClientContact",),
    ),
    "crm_opportunity": Entity(
        id="crm_opportunity",
        label="Opportunité avant-vente",
        module="CRM",
        definition="Projet commercial suivi avant signature, de la qualification au gagné/perdu.",
        source_models=("CRMOpportunity",),
        aliases=("affaire CRM", "prospect"),
    ),
    "measure_mission": Entity(
        id="measure_mission",
        label="Mission de métré",
        module="BE",
        definition="Collecte et vérification des cotes, photos et contraintes chantier.",
        source_models=("MeasureMission", "MeasureOpening", "MeasureMissionDocument"),
        aliases=("métré", "prise de cotes"),
    ),
    "technical_dossier": Entity(
        id="technical_dossier",
        label="Dossier technique BE",
        module="BE",
        definition="Dossier gouverné par le BE qui regroupe les versions de chiffrage, fabrication et débit.",
        source_models=("TechnicalDossier", "TechnicalDossierVersion"),
        aliases=("dossier BE", "dossier technique"),
    ),
    "technical_quotation": Entity(
        id="technical_quotation",
        label="Chiffrage technique",
        module="BE",
        definition="Résultat technique issu de PROGES, ORGADATA ou saisie interne servant à préparer le devis commercial.",
        source_models=("TechnicalDossierVersion",),
        aliases=("devis PROGES", "offre ORGADATA", "chiffrage PROGES/ORGADATA"),
    ),
    "commercial_quote": Entity(
        id="commercial_quote",
        label="Devis commercial MMG",
        module="DEVIS",
        definition="Proposition commerciale envoyable au client, avec prix, lignes et conditions MMG.",
        source_models=("SaleOrder", "SaleOrderLine"),
        aliases=("devis client", "proposition commerciale"),
    ),
    "signed_order": Entity(
        id="signed_order",
        label="Commande signée",
        module="COMMANDE",
        definition="Devis accepté ou signé qui autorise l'industrialisation puis la fabrication.",
        source_models=("SaleOrder",),
        aliases=("affaire gagnée", "commande client"),
    ),
    "industrial_dossier": Entity(
        id="industrial_dossier",
        label="Dossier industriel",
        module="FABRICATION",
        definition="Vue de production d'une commande signée, consolidant fabrication, débit et stock.",
        source_models=("SaleOrder", "TechnicalDossier", "ProductionOrder"),
    ),
    "fabrication_sheet": Entity(
        id="fabrication_sheet",
        label="Fiche fabrication",
        module="FABRICATION",
        definition="Document d'atelier décrivant comment fabriquer les ouvrages, sans valoir consommation matière.",
        source_models=("TechnicalDossierVersion",),
        aliases=("fiche fab", "document fabrication"),
    ),
    "cutting_sheet": Entity(
        id="cutting_sheet",
        label="Fiche de débit",
        module="DEBIT",
        definition="Liste matière à couper ou consommer, base de réservation puis débit atelier.",
        source_models=("TechnicalDossierVersion",),
        aliases=("liste débit", "débit matière", "fiche débit atelier"),
    ),
    "stock_item": Entity(
        id="stock_item",
        label="Référence matière stock",
        module="STOCK",
        definition="Article ou variante stockable identifié par fournisseur, référence, unité et emplacement.",
        source_models=("Product", "ProductVariant", "StockQuant", "StockLocation"),
        aliases=("profil", "accessoire", "matière"),
    ),
    "stock_location": Entity(
        id="stock_location",
        label="Emplacement physique stock",
        module="STOCK",
        definition="Zone, rack, casier ou point atelier où le stock réel peut être rangé, compté ou consommé.",
        source_models=("StockLocation",),
        aliases=("zone", "rack", "casier", "emplacement"),
    ),
    "stock_quant": Entity(
        id="stock_quant",
        label="Quantité physique localisée",
        module="STOCK",
        definition="Quantité réelle d'une variante sur un emplacement physique précis.",
        source_models=("StockQuant",),
        aliases=("stock réel", "quantité disponible"),
    ),
    "stock_reservation": Entity(
        id="stock_reservation",
        label="Réservation stock atelier",
        module="STOCK",
        definition="Blocage logique des références matière nécessaires à une fiche de débit pour une commande.",
        source_models=("StockReservation", "StockReservationLine"),
        aliases=("réservation matière",),
        required_before=("production_order",),
    ),
    "workshop_preparation": Entity(
        id="workshop_preparation",
        label="Bon de préparation atelier",
        module="STOCK",
        definition="Mise à disposition physique en zone atelier d'une réservation stock active.",
        source_models=("WorkshopPreparation", "WorkshopPreparationLine"),
    ),
    "production_order": Entity(
        id="production_order",
        label="Ordre de fabrication",
        module="FABRICATION",
        definition="Ordre atelier lancé après validation technique, stock et commande.",
        source_models=("ProductionOrder", "Planning"),
        aliases=("OF", "ordre atelier"),
        required_before=("real_workshop_debit",),
    ),
    "real_workshop_debit": Entity(
        id="real_workshop_debit",
        label="Débit atelier réel",
        module="DEBIT",
        definition="Consommation effective du stock après lancement fabrication et remise matière à l'atelier.",
        source_models=("StockMove",),
        aliases=("consommation matière", "débit réel"),
    ),
    "inventory_session": Entity(
        id="inventory_session",
        label="Campagne d'inventaire",
        module="STOCK",
        definition="Contrôle physique d'une zone ou d'un périmètre stock, avant justification et validation des écarts.",
        source_models=("InventorySession",),
        aliases=("inventaire physique", "campagne de comptage", "comptage stock"),
    ),
    "inventory_count_line": Entity(
        id="inventory_count_line",
        label="Ligne de comptage inventaire",
        module="STOCK",
        definition="Mesure physique d'une référence sur un emplacement, comparée au stock attendu et justifiée en cas d'écart.",
        source_models=("InventoryCountLine",),
        aliases=("ligne inventaire", "écart inventaire", "recompte"),
    ),
    "inventory_intelligence": Entity(
        id="inventory_intelligence",
        label="Score d'intelligence inventaire",
        module="STOCK",
        definition="Priorisation métier calculée depuis zones, écarts, valeur, mouvements, réservations et impact atelier/achat.",
        source_models=(
            "StockLocation",
            "StockQuant",
            "StockMove",
            "StockReservation",
            "InventorySession",
            "InventoryCountLine",
            "PurchaseOrderLine",
            "PurchaseRequestLine",
        ),
        aliases=("score inventaire", "priorité inventaire", "contrôle intelligent"),
    ),
    "supplier": Entity(
        id="supplier",
        label="Fournisseur",
        module="ACHATS",
        definition="Partenaire d'approvisionnement avec statut, conditions, délais et contacts opérationnels.",
        source_models=("Supplier",),
        aliases=("fournisseur", "partenaire achat"),
    ),
    "purchase_need": Entity(
        id="purchase_need",
        label="Besoin net achat",
        module="ACHATS",
        definition="Besoin calculé depuis stock exploitable, seuils, réservations, demandes et commandes ouvertes.",
        source_models=("ProductVariant", "StockQuant", "PurchaseRequestLine", "PurchaseOrderLine"),
        aliases=("besoin achat", "à commander", "réapprovisionnement"),
    ),
    "purchase_request": Entity(
        id="purchase_request",
        label="Demande d'achat",
        module="ACHATS",
        definition="Demande interne à valider avant engagement fournisseur lorsque l'achat est sensible.",
        source_models=("PurchaseRequest", "PurchaseRequestLine"),
        aliases=("DA", "demande appro"),
    ),
    "purchase_order": Entity(
        id="purchase_order",
        label="Commande fournisseur",
        module="ACHATS",
        definition="Bon de commande fournisseur engageant quantité, prix, délai et conditions d'achat.",
        source_models=("PurchaseOrder", "PurchaseOrderLine"),
        aliases=("bon fournisseur", "commande achat", "PO"),
    ),
    "purchase_receipt": Entity(
        id="purchase_receipt",
        label="Réception fournisseur",
        module="ACHATS",
        definition="Entrée physique d'une commande fournisseur dans un emplacement stock traçable.",
        source_models=("PurchaseOrderLine", "StockMove", "StockLocation"),
        aliases=("réception achat", "entrée fournisseur"),
    ),
    "supplier_invoice": Entity(
        id="supplier_invoice",
        label="Facture fournisseur",
        module="ACHATS",
        definition="Facture à rapprocher avec les lignes commandées et réceptionnées avant paiement.",
        source_models=("SupplierInvoice", "SupplierInvoiceLine"),
        aliases=("facture achat", "facture fournisseur"),
    ),
    "supplier_payment": Entity(
        id="supplier_payment",
        label="Paiement fournisseur",
        module="ACHATS",
        definition="Décaissement fournisseur lié à une facture validée ou partiellement soldée.",
        source_models=("SupplierPayment",),
        aliases=("paiement achat", "règlement fournisseur"),
    ),
    "supplier_dispute": Entity(
        id="supplier_dispute",
        label="Litige fournisseur",
        module="ACHATS",
        definition="Écart fournisseur bloquant potentiellement réception, facture ou paiement.",
        source_models=("SupplierDispute", "SupplierDisputeEvent", "SupplierDisputeAttachment"),
        aliases=("litige achat", "écart fournisseur", "blocage fournisseur"),
    ),
}


PIPELINE_SEQUENCE: tuple[str, ...] = (
    "client",
    "contact",
    "crm_opportunity",
    "measure_mission",
    "technical_quote",
    "technical_dossier",
    "commercial_quote",
    "signed_order",
    "industrial_file",
    "fabrication_sheet",
    "cutting_sheet",
    "stock_item",
    "stock_reservation",
    "production_order",
    "actual_cutting",
)

COMPAT_ENTITY_ALIASES = {
    "technical_quote": "technical_quotation",
    "industrial_file": "industrial_dossier",
    "actual_cutting": "real_workshop_debit",
}

BUSINESS_RULES = (
    "Un devis commercial doit rester traçable vers l'opportunité CRM.",
    "Une fabrication est interdite sans commande signée et dossier technique complet.",
    "Une réservation active est obligatoire avant la préparation atelier.",
    "Le débit réel est interdit avant le lancement fabrication et la remise matière atelier.",
    "Une fiche fabrication dit comment produire les ouvrages ; une fiche de débit dit quoi consommer.",
)


RELATIONS: tuple[Relation, ...] = (
    Relation("client", "has_contact", "contact"),
    Relation("client", "opens", "crm_opportunity", required=True),
    Relation("crm_opportunity", "may_require", "measure_mission"),
    Relation("measure_mission", "creates", "technical_dossier", required=True),
    Relation("technical_dossier", "contains", "technical_quotation"),
    Relation("technical_dossier", "contains", "fabrication_sheet"),
    Relation("technical_dossier", "contains", "cutting_sheet"),
    Relation("technical_quotation", "prepares", "commercial_quote"),
    Relation("crm_opportunity", "is_priced_by", "commercial_quote"),
    Relation("commercial_quote", "becomes_when_signed", "signed_order"),
    Relation("crm_opportunity", "is_won_by", "signed_order"),
    Relation("signed_order", "authorizes", "industrial_dossier", required=True),
    Relation("industrial_dossier", "requires", "fabrication_sheet", required=True),
    Relation("industrial_dossier", "requires", "cutting_sheet", required=True),
    Relation("stock_quant", "locates", "stock_item", required=True),
    Relation("stock_quant", "is_stored_in", "stock_location", required=True),
    Relation("stock_item", "is_available_through", "stock_quant"),
    Relation("stock_location", "contains", "stock_quant"),
    Relation("cutting_sheet", "reserves", "stock_reservation"),
    Relation("stock_reservation", "reserves", "stock_item"),
    Relation("stock_reservation", "anchors_to", "stock_location"),
    Relation("stock_reservation", "is_prepared_by", "workshop_preparation"),
    Relation("inventory_session", "controls", "stock_location", required=True),
    Relation("inventory_session", "contains", "inventory_count_line", required=True),
    Relation("inventory_count_line", "measures", "stock_item", required=True),
    Relation("inventory_count_line", "counts_at", "stock_location", required=True),
    Relation("inventory_count_line", "may_adjust", "stock_quant"),
    Relation("inventory_intelligence", "prioritizes", "inventory_session"),
    Relation("inventory_intelligence", "scores", "stock_location"),
    Relation("inventory_intelligence", "scores", "stock_item"),
    Relation("inventory_intelligence", "uses_signal_from", "stock_reservation"),
    Relation("inventory_intelligence", "uses_signal_from", "real_workshop_debit"),
    Relation("stock_item", "is_supplied_by", "supplier"),
    Relation("supplier", "supplies", "stock_item"),
    Relation("purchase_need", "is_generated_from", "stock_item", required=True),
    Relation("purchase_need", "uses_signal_from", "stock_quant"),
    Relation("purchase_need", "uses_signal_from", "stock_reservation"),
    Relation("purchase_need", "uses_signal_from", "purchase_request"),
    Relation("purchase_need", "uses_signal_from", "purchase_order"),
    Relation("purchase_request", "covers", "purchase_need"),
    Relation("purchase_request", "targets", "supplier"),
    Relation("purchase_order", "fulfills", "purchase_request"),
    Relation("purchase_order", "orders_from", "supplier", required=True),
    Relation("purchase_order", "covers", "purchase_need"),
    Relation("purchase_order", "contains", "stock_item"),
    Relation("purchase_receipt", "receives", "purchase_order", required=True),
    Relation("purchase_receipt", "receives_into", "stock_location", required=True),
    Relation("purchase_receipt", "updates", "stock_quant"),
    Relation("supplier_invoice", "reconciles", "purchase_order", required=True),
    Relation("supplier_payment", "settles", "supplier_invoice", required=True),
    Relation("supplier_dispute", "blocks", "purchase_order"),
    Relation("supplier_dispute", "blocks", "supplier_invoice"),
    Relation("supplier_dispute", "concerns", "supplier", required=True),
    Relation("signed_order", "authorizes", "production_order"),
    Relation("production_order", "uses", "fabrication_sheet"),
    Relation("production_order", "consumes_via", "real_workshop_debit"),
    Relation("real_workshop_debit", "must_trace_to", "cutting_sheet", required=True),
    Relation("real_workshop_debit", "consumes", "stock_item"),
    Relation("real_workshop_debit", "moves_from", "stock_location"),
)


EXTERNAL_DOCUMENT_MAPPINGS: tuple[ExternalDocumentMapping, ...] = (
    ExternalDocumentMapping(
        source_system="PROGES",
        document_type="QUOTING",
        canonical_entity="technical_quotation",
        label="Devis ou chiffrage PROGES PVC",
        definition="Base technique de prix et composants PVC ; ne vaut pas commande client.",
        forbidden_confusions=("commercial_quote", "signed_order", "cutting_sheet"),
    ),
    ExternalDocumentMapping(
        source_system="PROGES",
        document_type="CUTTING",
        canonical_entity="cutting_sheet",
        label="Fiche de débit PROGES PVC",
        definition="Liste matière PVC à réserver puis couper/consommer.",
        forbidden_confusions=("technical_quotation", "fabrication_sheet", "real_workshop_debit"),
    ),
    ExternalDocumentMapping(
        source_system="PROGES",
        document_type="FABRICATION",
        canonical_entity="fabrication_sheet",
        label="Fiche fabrication PROGES PVC",
        definition="Instructions de fabrication PVC ; ne déclenche pas seule la consommation stock.",
        forbidden_confusions=("cutting_sheet", "real_workshop_debit"),
    ),
    ExternalDocumentMapping(
        source_system="PROGES",
        document_type="VALUATION",
        canonical_entity="technical_quotation",
        label="Valorisation PROGES PVC",
        definition="Récapitulatif économique PVC utilisé comme contrôle, pas comme commande client.",
        forbidden_confusions=("signed_order", "cutting_sheet", "real_workshop_debit"),
    ),
    ExternalDocumentMapping(
        source_system="ORGADATA",
        document_type="QUOTING",
        canonical_entity="technical_quotation",
        label="Offre ou devis ORGADATA ALU",
        definition="Base technique ALU permettant de préparer la proposition commerciale MMG.",
        forbidden_confusions=("commercial_quote", "signed_order", "cutting_sheet"),
    ),
    ExternalDocumentMapping(
        source_system="ORGADATA",
        document_type="FABRICATION",
        canonical_entity="fabrication_sheet",
        label="Fiche fabrication ORGADATA ALU",
        definition="Instructions de fabrication atelier ; ne déclenche pas seule la consommation stock.",
        forbidden_confusions=("cutting_sheet", "real_workshop_debit"),
    ),
    ExternalDocumentMapping(
        source_system="ORGADATA",
        document_type="CUTTING",
        canonical_entity="cutting_sheet",
        label="Liste débit ORGADATA ALU",
        definition="Liste matière ALU à réserver puis débiter.",
        forbidden_confusions=("fabrication_sheet", "technical_quotation", "real_workshop_debit"),
    ),
    ExternalDocumentMapping(
        source_system="ORGADATA",
        document_type="VALUATION",
        canonical_entity="technical_quotation",
        label="Valorisation ORGADATA ALU",
        definition="Récapitulatif économique ALU utilisé comme contrôle, pas comme commande client.",
        forbidden_confusions=("signed_order", "cutting_sheet", "real_workshop_debit"),
    ),
)


WORKFLOW_GATES: tuple[WorkflowGate, ...] = (
    WorkflowGate(
        id="quote_requires_opportunity",
        label="Un devis commercial appartient à une opportunité",
        from_entity="crm_opportunity",
        to_entity="commercial_quote",
        required_entities=("crm_opportunity",),
        rule="Tout SaleOrder commercial doit rester traçable vers une opportunité CRM quand il provient de l'avant-vente.",
    ),
    WorkflowGate(
        id="production_requires_signed_order",
        label="Fabrication interdite sans commande signée",
        from_entity="signed_order",
        to_entity="production_order",
        required_entities=("signed_order", "fabrication_sheet", "cutting_sheet"),
        rule="Le lancement atelier nécessite une commande validée/signée et un dossier technique complet.",
    ),
    WorkflowGate(
        id="reservation_requires_cutting_sheet",
        label="Réservation stock basée sur une fiche de débit",
        from_entity="cutting_sheet",
        to_entity="stock_reservation",
        required_entities=("cutting_sheet",),
        rule="Une réservation atelier doit être issue d'une fiche de débit typée CUTTING, pas d'une fiche fabrication.",
    ),
    WorkflowGate(
        id="debit_requires_active_reservation",
        label="Débit réel après réservation active et remise atelier",
        from_entity="stock_reservation",
        to_entity="real_workshop_debit",
        required_entities=("stock_reservation", "workshop_preparation", "production_order"),
        rule="Le débit réel consomme le stock seulement après réservation active, préparation remise et fabrication lancée.",
    ),
    WorkflowGate(
        id="inventory_requires_clear_location",
        label="Inventaire physique sur emplacement exploitable",
        from_entity="stock_location",
        to_entity="inventory_session",
        required_entities=("stock_location",),
        rule="Une campagne d'inventaire doit cibler un emplacement interne actif et suffisamment précis pour isoler le comptage.",
    ),
    WorkflowGate(
        id="inventory_adjustment_requires_validated_count",
        label="Ajustement stock après comptage validé",
        from_entity="inventory_count_line",
        to_entity="stock_quant",
        required_entities=("inventory_session", "inventory_count_line", "stock_location", "stock_item"),
        rule="Un ajustement de stock ne peut être créé qu'après validation d'une campagne, avec écart compté et motif justifié.",
    ),
    WorkflowGate(
        id="inventory_intelligence_requires_live_stock_data",
        label="Score inventaire alimenté par données réelles",
        from_entity="stock_quant",
        to_entity="inventory_intelligence",
        required_entities=("stock_quant", "stock_location", "stock_item"),
        rule="Le score inventaire doit croiser stock localisé, qualité de zone, écarts, mouvements, réservations et impact achat/atelier.",
    ),
    WorkflowGate(
        id="purchase_need_requires_stock_and_supplier_context",
        label="Besoin achat calculé depuis stock et fournisseur",
        from_entity="stock_item",
        to_entity="purchase_need",
        required_entities=("stock_item", "stock_quant", "supplier"),
        rule="Un besoin net achat doit croiser stock exploitable, seuil, besoins futurs, fournisseur actif et couverture achat ouverte.",
    ),
    WorkflowGate(
        id="purchase_order_requires_approved_request_or_permission",
        label="Commande fournisseur contrôlée",
        from_entity="purchase_request",
        to_entity="purchase_order",
        required_entities=("purchase_need", "supplier"),
        rule="Une commande fournisseur doit couvrir un besoin achat qualifié ou être créée par un rôle achats habilité, avec fournisseur non bloqué.",
    ),
    WorkflowGate(
        id="purchase_receipt_requires_clear_location",
        label="Réception fournisseur sur emplacement clair",
        from_entity="purchase_order",
        to_entity="purchase_receipt",
        required_entities=("purchase_order", "stock_location"),
        rule="Une réception fournisseur doit alimenter un emplacement réel exploitable pour fiabiliser stock et inventaire.",
    ),
    WorkflowGate(
        id="supplier_invoice_requires_received_purchase_order",
        label="Facture rapprochée avec commande reçue",
        from_entity="purchase_order",
        to_entity="supplier_invoice",
        required_entities=("purchase_order", "purchase_receipt"),
        rule="Une facture fournisseur doit être rapprochée des quantités commandées et réceptionnées avant paiement.",
    ),
)


PIPELINE: tuple[str, ...] = (
    "client",
    "crm_opportunity",
    "measure_mission",
    "technical_dossier",
    "technical_quotation",
    "commercial_quote",
    "signed_order",
    "industrial_dossier",
    "fabrication_sheet",
    "cutting_sheet",
    "stock_reservation",
    "workshop_preparation",
    "production_order",
    "real_workshop_debit",
)


STOCK_CONTROL_PATH: tuple[str, ...] = (
    "stock_location",
    "stock_quant",
    "stock_item",
    "inventory_intelligence",
    "inventory_session",
    "inventory_count_line",
    "stock_quant",
)


PROCUREMENT_PATH: tuple[str, ...] = (
    "stock_item",
    "purchase_need",
    "supplier",
    "purchase_request",
    "purchase_order",
    "purchase_receipt",
    "supplier_invoice",
    "supplier_dispute",
    "supplier_payment",
)


BUSINESS_RULES: tuple[str, ...] = tuple(gate.rule for gate in WORKFLOW_GATES)


MODEL_BINDINGS: dict[str, tuple[str, ...]] = {
    entity_id: entity.source_models for entity_id, entity in ENTITIES.items()
}


ENTITY_STATUSES: dict[str, tuple[EntityStatus, ...]] = {
    "crm_opportunity": (
        EntityStatus("crm_opportunity", "nouveau", "Nouvelle"),
        EntityStatus("crm_opportunity", "qualifie", "Qualifiée"),
        EntityStatus("crm_opportunity", "metre_a_planifier", "Métré à planifier"),
        EntityStatus("crm_opportunity", "metre_en_cours", "Métré en cours"),
        EntityStatus("crm_opportunity", "proposition_a_preparer", "Proposition à préparer"),
        EntityStatus("crm_opportunity", "proposition_a_valider", "Proposition à valider"),
        EntityStatus("crm_opportunity", "proposition_envoyee", "Proposition envoyée"),
        EntityStatus("crm_opportunity", "negociation", "Négociation"),
        EntityStatus("crm_opportunity", "gagne", "Gagnée", final=True),
        EntityStatus("crm_opportunity", "perdu", "Perdue", final=True),
    ),
    "measure_mission": (
        EntityStatus("measure_mission", "DRAFT", "Brouillon"),
        EntityStatus("measure_mission", "PLANNED", "Planifiée"),
        EntityStatus("measure_mission", "IN_PROGRESS", "En cours"),
        EntityStatus("measure_mission", "UNDER_REVIEW", "En contrôle BE"),
        EntityStatus("measure_mission", "VALIDATED", "Validée BE", final=True),
        EntityStatus("measure_mission", "CANCELLED", "Annulée", final=True),
    ),
    "technical_dossier": (
        EntityStatus("technical_dossier", "DRAFT", "Brouillon"),
        EntityStatus("technical_dossier", "UNDER_REVIEW", "En contrôle BE"),
        EntityStatus("technical_dossier", "APPROVED", "Validé BE", final=True),
        EntityStatus("technical_dossier", "REJECTED", "À corriger"),
    ),
    "commercial_quote": (
        EntityStatus("commercial_quote", "DRAFT", "Brouillon"),
        EntityStatus("commercial_quote", "SENT", "Envoyé"),
        EntityStatus("commercial_quote", "SIGNED", "Signé", final=True),
        EntityStatus("commercial_quote", "CANCELLED", "Annulé", final=True),
    ),
    "signed_order": (
        EntityStatus("signed_order", "SIGNED", "Signée"),
        EntityStatus("signed_order", "READY_FOR_PRODUCTION", "Prête pour production"),
        EntityStatus("signed_order", "IN_PRODUCTION", "En production"),
        EntityStatus("signed_order", "COMPLETED", "Terminée", final=True),
    ),
    "stock_reservation": (
        EntityStatus("stock_reservation", "DRAFT", "Brouillon"),
        EntityStatus("stock_reservation", "ACTIVE", "Active"),
        EntityStatus("stock_reservation", "CONSUMED", "Consommée", final=True),
        EntityStatus("stock_reservation", "CANCELLED", "Annulée", final=True),
    ),
    "inventory_session": (
        EntityStatus("inventory_session", "scheduled", "Planifiée"),
        EntityStatus("inventory_session", "draft", "Brouillon"),
        EntityStatus("inventory_session", "counting", "Comptage"),
        EntityStatus("inventory_session", "pending_approval", "Approbation"),
        EntityStatus("inventory_session", "validated", "Validée", final=True),
        EntityStatus("inventory_session", "cancelled", "Annulée", final=True),
    ),
    "inventory_count_line": (
        EntityStatus("inventory_count_line", "pending", "À compter"),
        EntityStatus("inventory_count_line", "ok", "Conforme"),
        EntityStatus("inventory_count_line", "variance", "Écart"),
        EntityStatus("inventory_count_line", "recount", "À recompter"),
        EntityStatus("inventory_count_line", "validated", "Validée", final=True),
    ),
    "inventory_intelligence": (
        EntityStatus("inventory_intelligence", "low", "Stable"),
        EntityStatus("inventory_intelligence", "medium", "À surveiller"),
        EntityStatus("inventory_intelligence", "high", "Prioritaire"),
        EntityStatus("inventory_intelligence", "critical", "Critique"),
    ),
    "supplier": (
        EntityStatus("supplier", "ACTIVE", "Actif"),
        EntityStatus("supplier", "TO_QUALIFY", "À qualifier"),
        EntityStatus("supplier", "STRATEGIC", "Stratégique"),
        EntityStatus("supplier", "BLOCKED", "Bloqué"),
    ),
    "purchase_need": (
        EntityStatus("purchase_need", "CRITICAL", "Critique"),
        EntityStatus("purchase_need", "URGENT", "Urgent"),
        EntityStatus("purchase_need", "TO_PLAN", "À planifier"),
        EntityStatus("purchase_need", "BLOCKED", "Bloqué"),
        EntityStatus("purchase_need", "COVERED", "Couvert", final=True),
    ),
    "purchase_request": (
        EntityStatus("purchase_request", "DRAFT", "Brouillon"),
        EntityStatus("purchase_request", "PENDING_APPROVAL", "À valider"),
        EntityStatus("purchase_request", "APPROVED", "Validée"),
        EntityStatus("purchase_request", "REJECTED", "Refusée", final=True),
        EntityStatus("purchase_request", "CONVERTED", "Convertie", final=True),
        EntityStatus("purchase_request", "CANCELLED", "Annulée", final=True),
    ),
    "purchase_order": (
        EntityStatus("purchase_order", "DRAFT", "Brouillon"),
        EntityStatus("purchase_order", "SENT", "Envoyée fournisseur"),
        EntityStatus("purchase_order", "PARTIAL", "Réception partielle"),
        EntityStatus("purchase_order", "RECEIVED", "Réceptionnée", final=True),
        EntityStatus("purchase_order", "CANCELLED", "Annulée", final=True),
    ),
    "supplier_invoice": (
        EntityStatus("supplier_invoice", "TO_PAY", "À payer"),
        EntityStatus("supplier_invoice", "PARTIAL", "Partiellement payée"),
        EntityStatus("supplier_invoice", "PAID", "Payée", final=True),
        EntityStatus("supplier_invoice", "CANCELLED", "Annulée", final=True),
    ),
    "supplier_dispute": (
        EntityStatus("supplier_dispute", "OPEN", "Ouvert"),
        EntityStatus("supplier_dispute", "IN_PROGRESS", "En traitement"),
        EntityStatus("supplier_dispute", "RESOLVED", "Résolu", final=True),
        EntityStatus("supplier_dispute", "CANCELLED", "Annulé", final=True),
    ),
    "production_order": (
        EntityStatus("production_order", "PLANNED", "Planifié"),
        EntityStatus("production_order", "LAUNCHED", "Lancé"),
        EntityStatus("production_order", "DONE", "Terminé", final=True),
    ),
    "real_workshop_debit": (
        EntityStatus("real_workshop_debit", "PENDING", "À débiter"),
        EntityStatus("real_workshop_debit", "CONSUMED", "Débité", final=True),
    ),
}


BUSINESS_EVENTS: tuple[BusinessEvent, ...] = (
    BusinessEvent(
        "crm_opportunity_created",
        "Opportunité créée",
        "crm_opportunity",
        None,
        "Création d'un dossier avant-vente rattaché à un client.",
    ),
    BusinessEvent(
        "measure_submitted_to_be",
        "Métré soumis au BE",
        "measure_mission",
        "technical_dossier",
        "Passage des cotes terrain en contrôle technique.",
    ),
    BusinessEvent(
        "technical_dossier_validated",
        "Dossier technique validé BE",
        "technical_dossier",
        "commercial_quote",
        "Validation technique permettant de préparer ou confirmer le devis.",
    ),
    BusinessEvent(
        "quote_sent",
        "Devis envoyé",
        "commercial_quote",
        "client",
        "Transmission contrôlée de la proposition commerciale au client.",
    ),
    BusinessEvent(
        "quote_signed",
        "Devis signé",
        "commercial_quote",
        "signed_order",
        "Acceptation client transformant la proposition en commande.",
    ),
    BusinessEvent(
        "stock_reserved",
        "Stock réservé",
        "cutting_sheet",
        "stock_reservation",
        "Réservation des matières à partir d'une fiche de débit.",
    ),
    BusinessEvent(
        "workshop_prepared",
        "Bon atelier préparé",
        "stock_reservation",
        "workshop_preparation",
        "Mise à disposition des matières réservées pour l'atelier.",
    ),
    BusinessEvent(
        "production_launched",
        "Fabrication lancée",
        "production_order",
        "real_workshop_debit",
        "Autorisation atelier précédant la consommation matière réelle.",
    ),
    BusinessEvent(
        "stock_consumed",
        "Débit consommé",
        "real_workshop_debit",
        "stock_item",
        "Sortie effective des quantités matière du stock.",
    ),
    BusinessEvent(
        "inventory_scored",
        "Priorité inventaire calculée",
        "inventory_intelligence",
        "inventory_session",
        "Analyse des zones et références à compter en priorité depuis les données stock, atelier et achat.",
    ),
    BusinessEvent(
        "inventory_scheduled",
        "Inventaire planifié",
        "stock_location",
        "inventory_session",
        "Création d'une campagne de comptage sur une zone physique exploitable.",
    ),
    BusinessEvent(
        "inventory_counted",
        "Ligne inventaire comptée",
        "inventory_session",
        "inventory_count_line",
        "Saisie d'une quantité réelle pour une référence et un emplacement donnés.",
    ),
    BusinessEvent(
        "inventory_variance_detected",
        "Écart inventaire détecté",
        "inventory_count_line",
        "stock_item",
        "Détection d'un écart entre stock attendu et stock compté.",
    ),
    BusinessEvent(
        "inventory_validated",
        "Inventaire validé",
        "inventory_session",
        "stock_quant",
        "Validation finale de la campagne et préparation des ajustements stock tracés.",
    ),
    BusinessEvent(
        "stock_adjusted",
        "Stock ajusté après inventaire",
        "inventory_count_line",
        "stock_quant",
        "Création d'un mouvement d'ajustement stock à partir d'une ligne inventaire validée.",
    ),
    BusinessEvent(
        "purchase_need_detected",
        "Besoin achat détecté",
        "purchase_need",
        "stock_item",
        "Calcul d'un besoin net depuis seuil, stock, réservations et couverture achat.",
    ),
    BusinessEvent(
        "purchase_request_created",
        "Demande d'achat créée",
        "purchase_need",
        "purchase_request",
        "Transformation d'un besoin net qualifié en demande interne achats.",
    ),
    BusinessEvent(
        "purchase_request_approved",
        "Demande d'achat validée",
        "purchase_request",
        "purchase_order",
        "Validation permettant la création ou conversion en commande fournisseur.",
    ),
    BusinessEvent(
        "purchase_order_sent",
        "Commande fournisseur envoyée",
        "purchase_order",
        "supplier",
        "Engagement fournisseur avec quantités, prix, délai et conditions.",
    ),
    BusinessEvent(
        "purchase_received",
        "Réception fournisseur enregistrée",
        "purchase_order",
        "purchase_receipt",
        "Entrée physique d'une commande fournisseur dans un emplacement stock.",
    ),
    BusinessEvent(
        "supplier_invoice_reconciled",
        "Facture fournisseur rapprochée",
        "supplier_invoice",
        "purchase_order",
        "Contrôle facture contre commande et réception avant paiement.",
    ),
    BusinessEvent(
        "supplier_dispute_opened",
        "Litige fournisseur ouvert",
        "supplier_dispute",
        "supplier",
        "Création d'un blocage ou d'une action fournisseur sur écart prix, quantité, qualité ou délai.",
    ),
    BusinessEvent(
        "supplier_payment_recorded",
        "Paiement fournisseur enregistré",
        "supplier_payment",
        "supplier_invoice",
        "Décaissement fournisseur traçable après rapprochement et absence de blocage.",
    ),
)


STEP_RBAC: tuple[StepPermission, ...] = (
    StepPermission("client", "read", "SALES_VIEW", "Consulter les fiches clients."),
    StepPermission("client", "write", "SALES_EDIT", "Créer ou modifier les fiches clients."),
    StepPermission("crm_opportunity", "read", "SALES_VIEW", "Consulter le pipeline avant-vente."),
    StepPermission("crm_opportunity", "write", "SALES_EDIT", "Créer, qualifier ou déplacer une opportunité."),
    StepPermission("measure_mission", "read", "SALES_VIEW", "Consulter les missions de métré depuis le CRM."),
    StepPermission("measure_mission", "write", "SALES_EDIT", "Créer ou soumettre une mission de métré."),
    StepPermission("technical_dossier", "review", "SALES_EDIT", "Soumettre le dossier technique ; la validation reste réservée aux rôles BE habilités."),
    StepPermission("commercial_quote", "write", "SALES_EDIT", "Préparer et envoyer un devis commercial."),
    StepPermission("signed_order", "convert", "SALES_EDIT", "Transformer un devis accepté en commande."),
    StepPermission("stock_reservation", "write", "workshop.reserve_stock", "Créer ou annuler une réservation matière."),
    StepPermission("workshop_preparation", "write", "stock.transfer", "Préparer, remettre ou retourner le bon atelier."),
    StepPermission("production_order", "launch", "SALES_EDIT", "Transmettre la commande préparée à l'atelier ; l'autorisation reste contrôlée par les rôles de lancement."),
    StepPermission("real_workshop_debit", "consume", "workshop.consume_stock", "Débiter réellement la matière."),
    StepPermission("stock_location", "manage", "stock.locations.manage", "Créer, clarifier ou archiver les emplacements physiques."),
    StepPermission("inventory_session", "count", "inventory.count", "Compter les références d'une campagne d'inventaire."),
    StepPermission("inventory_session", "validate", "inventory.validate", "Créer, démarrer, valider ou annuler une campagne d'inventaire."),
    StepPermission("inventory_session", "approve_value", "inventory.approve_value", "Approuver un écart d'inventaire valorisé avant ajustement."),
    StepPermission("inventory_intelligence", "read", "inventory.count", "Consulter les priorités inventaire calculées depuis les données stock."),
    StepPermission("supplier", "read", "PURCHASES_VIEW", "Consulter le référentiel fournisseurs."),
    StepPermission("supplier", "write", "purchases.order", "Créer ou modifier un fournisseur et ses conditions achat."),
    StepPermission("purchase_need", "read", "PURCHASES_VIEW", "Consulter les besoins nets achat calculés."),
    StepPermission("purchase_request", "write", "purchases.request", "Créer une demande d'achat depuis un besoin net."),
    StepPermission("purchase_request", "approve", "purchases.approve", "Valider ou refuser une demande d'achat."),
    StepPermission("purchase_order", "write", "purchases.order", "Créer, modifier ou envoyer un bon fournisseur."),
    StepPermission("purchase_receipt", "receive", "purchases.receive", "Réceptionner une commande fournisseur dans le stock."),
    StepPermission("supplier_invoice", "reconcile", "purchases.invoice.manage", "Rapprocher une facture fournisseur avec commande et réception."),
    StepPermission("supplier_payment", "pay", "purchases.payments.manage", "Enregistrer un paiement fournisseur."),
    StepPermission("supplier_dispute", "write", "purchases.order", "Créer ou traiter un litige fournisseur."),
)


def document_type_can_feed_stock(document_type: str) -> bool:
    """Vrai uniquement pour une fiche de débit exploitable par le stock."""

    normalized_type = document_type.strip().upper()
    return bool(DOCUMENT_TYPES.get(normalized_type, {}).get("stock_source", False))


def _compat_entity(code: str) -> Entity:
    canonical_code = COMPAT_ENTITY_ALIASES.get(code, code)
    entity = ENTITIES[canonical_code]
    if code == "actual_cutting":
        return Entity(
            id="actual_cutting",
            label="Débit réel",
            module="DEBIT",
            definition=entity.definition,
            source_models=entity.source_models,
            aliases=entity.aliases,
            required_before=entity.required_before,
        )
    if code == "technical_quote":
        return Entity(
            id="technical_quote",
            label=entity.label,
            module=entity.module,
            definition=entity.definition,
            source_models=entity.source_models,
            aliases=entity.aliases,
            required_before=entity.required_before,
        )
    if code == "industrial_file":
        return Entity(
            id="industrial_file",
            label=entity.label,
            module=entity.module,
            definition=entity.definition,
            source_models=entity.source_models,
            aliases=entity.aliases,
            required_before=entity.required_before,
        )
    return entity


def canonical_path() -> tuple[Entity, ...]:
    """Retourne le chemin métier historique lisible par l'UI/IA."""

    return tuple(_compat_entity(code) for code in PIPELINE_SEQUENCE)


def entities_by_module(module: str) -> tuple[Entity, ...]:
    """Filtre les entités par module, avec l'alias historique Atelier."""

    normalized_module = module.strip().upper()
    if normalized_module == "ATELIER":
        atelier_codes = {
            "industrial_file",
            "fabrication_sheet",
            "cutting_sheet",
            "production_order",
            "actual_cutting",
        }
        return tuple(_compat_entity(code) for code in PIPELINE_SEQUENCE if code in atelier_codes)
    return tuple(entity for entity in ENTITIES.values() if entity.module.upper() == normalized_module)


def ontology_as_dict() -> dict[str, object]:
    """Retourne une représentation sérialisable de l'ontologie."""

    return {
        "modules": list(MMG_MODULES),
        "pipeline": list(PIPELINE),
        "stock_control_path": list(STOCK_CONTROL_PATH),
        "procurement_path": list(PROCUREMENT_PATH),
        "entities": {key: entity.__dict__ for key, entity in ENTITIES.items()},
        "relations": [relation.__dict__ for relation in RELATIONS],
        "model_bindings": MODEL_BINDINGS,
        "entity_statuses": {
            entity_id: [status.__dict__ for status in statuses]
            for entity_id, statuses in ENTITY_STATUSES.items()
        },
        "external_document_mappings": [
            mapping.__dict__ for mapping in EXTERNAL_DOCUMENT_MAPPINGS
        ],
        "business_events": [event.__dict__ for event in BUSINESS_EVENTS],
        "step_rbac": [permission.__dict__ for permission in STEP_RBAC],
        "workflow_gates": [gate.__dict__ for gate in WORKFLOW_GATES],
    }


def resolve_external_document(
    source_system: str,
    document_type: str,
) -> ExternalDocumentMapping | None:
    """Associe un document PROGES/ORGADATA à l'objet canonique MMG."""

    normalized_source = source_system.strip().upper()
    normalized_type = document_type.strip().upper()
    return next(
        (
            mapping
            for mapping in EXTERNAL_DOCUMENT_MAPPINGS
            if mapping.source_system == normalized_source
            and mapping.document_type == normalized_type
        ),
        None,
    )


def document_mapping(
    source_system: str,
    document_type: str,
) -> ExternalDocumentMapping:
    """Compatibilité historique : QUOTE est normalisé en QUOTING."""

    normalized_type = document_type.strip().upper()
    if normalized_type == "QUOTE":
        normalized_type = "QUOTING"
    mapping = resolve_external_document(source_system, normalized_type)
    if not mapping:
        raise ValueError(f"Document externe inconnu: {source_system}/{document_type}")
    compat_entity = {
        "technical_quotation": "technical_quote",
        "real_workshop_debit": "actual_cutting",
    }.get(mapping.canonical_entity, mapping.canonical_entity)
    return ExternalDocumentMapping(
        source_system=mapping.source_system,
        document_type="QUOTE" if mapping.document_type == "QUOTING" else mapping.document_type,
        canonical_entity=compat_entity,
        label=mapping.label,
        definition=mapping.definition,
        forbidden_confusions=mapping.forbidden_confusions,
    )


def validate_ontology() -> list[str]:
    """Retourne les incohérences structurelles de l'ontologie."""

    issues: list[str] = []
    entity_ids = set(ENTITIES)

    for entity_id, entity in ENTITIES.items():
        if entity.id != entity_id:
            issues.append(f"Entity key/id mismatch: {entity_id} != {entity.id}")
        if entity.module not in MMG_MODULES:
            issues.append(f"Unknown module for {entity_id}: {entity.module}")

    for relation in RELATIONS:
        if relation.source not in entity_ids:
            issues.append(f"Unknown relation source: {relation.source}")
        if relation.target not in entity_ids:
            issues.append(f"Unknown relation target: {relation.target}")

    for mapping in EXTERNAL_DOCUMENT_MAPPINGS:
        if mapping.canonical_entity not in entity_ids:
            issues.append(f"Unknown mapping entity: {mapping.canonical_entity}")
        for confused_entity in mapping.forbidden_confusions:
            if confused_entity not in entity_ids:
                issues.append(f"Unknown forbidden confusion: {confused_entity}")
            if confused_entity == mapping.canonical_entity:
                issues.append(
                    f"Mapping cannot forbid its own canonical entity: {mapping.canonical_entity}"
                )

    for gate in WORKFLOW_GATES:
        if gate.from_entity not in entity_ids:
            issues.append(f"Unknown gate source: {gate.from_entity}")
        if gate.to_entity not in entity_ids:
            issues.append(f"Unknown gate target: {gate.to_entity}")
        for required_entity in gate.required_entities:
            if required_entity not in entity_ids:
                issues.append(f"Unknown gate requirement: {required_entity}")

    for entity_id, statuses in ENTITY_STATUSES.items():
        if entity_id not in entity_ids:
            issues.append(f"Unknown status entity: {entity_id}")
        for status in statuses:
            if status.entity != entity_id:
                issues.append(
                    f"Status entity mismatch: {entity_id} != {status.entity}"
                )

    for event in BUSINESS_EVENTS:
        if event.source_entity not in entity_ids:
            issues.append(f"Unknown event source: {event.source_entity}")
        if event.target_entity is not None and event.target_entity not in entity_ids:
            issues.append(f"Unknown event target: {event.target_entity}")

    for permission in STEP_RBAC:
        if permission.entity not in entity_ids:
            issues.append(f"Unknown RBAC entity: {permission.entity}")
        if not permission.permission:
            issues.append(f"Missing permission for {permission.entity}/{permission.action}")

    return issues
