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
    Relation("cutting_sheet", "reserves", "stock_reservation"),
    Relation("stock_reservation", "reserves", "stock_item"),
    Relation("stock_reservation", "is_prepared_by", "workshop_preparation"),
    Relation("signed_order", "authorizes", "production_order"),
    Relation("production_order", "uses", "fabrication_sheet"),
    Relation("production_order", "consumes_via", "real_workshop_debit"),
    Relation("real_workshop_debit", "must_trace_to", "cutting_sheet", required=True),
    Relation("real_workshop_debit", "consumes", "stock_item"),
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
)


STEP_RBAC: tuple[StepPermission, ...] = (
    StepPermission("client", "read", "SALES_VIEW", "Consulter les fiches clients."),
    StepPermission("client", "write", "SALES_EDIT", "Créer ou modifier les fiches clients."),
    StepPermission("crm_opportunity", "read", "SALES_VIEW", "Consulter le pipeline avant-vente."),
    StepPermission("crm_opportunity", "write", "SALES_EDIT", "Créer, qualifier ou déplacer une opportunité."),
    StepPermission("measure_mission", "read", "SALES_VIEW", "Consulter les missions de métré depuis le CRM."),
    StepPermission("measure_mission", "write", "SALES_EDIT", "Créer ou soumettre une mission de métré."),
    StepPermission("technical_dossier", "review", "PRODUCTION_MANAGE", "Valider ou rejeter le dossier technique BE."),
    StepPermission("commercial_quote", "write", "SALES_EDIT", "Préparer et envoyer un devis commercial."),
    StepPermission("signed_order", "convert", "SALES_EDIT", "Transformer un devis accepté en commande."),
    StepPermission("stock_reservation", "write", "STOCK_MANAGE", "Créer ou annuler une réservation matière."),
    StepPermission("workshop_preparation", "write", "STOCK_MANAGE", "Préparer et remettre le bon atelier."),
    StepPermission("production_order", "launch", "PRODUCTION_MANAGE", "Lancer la fabrication."),
    StepPermission("real_workshop_debit", "consume", "STOCK_MANAGE", "Débiter réellement la matière."),
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
