from backend.domain.ontology import (
    ENTITIES,
    EXTERNAL_DOCUMENT_MAPPINGS,
    PIPELINE,
    RELATIONS,
    WORKFLOW_GATES,
    document_type_can_feed_stock,
    ontology_as_dict,
    resolve_external_document,
    validate_ontology,
)


def test_business_ontology_is_structurally_consistent():
    assert validate_ontology() == []


def test_business_ontology_declares_end_to_end_industrial_path():
    assert PIPELINE == (
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
    assert ENTITIES[PIPELINE[0]].label == "Client"
    assert ENTITIES[PIPELINE[-1]].label == "Débit atelier réel"


def test_proges_and_orgadata_documents_are_mapped_to_canonical_entities():
    assert resolve_external_document("PROGES", "QUOTING").canonical_entity == "technical_quotation"
    assert resolve_external_document("PROGES", "CUTTING").canonical_entity == "cutting_sheet"
    assert resolve_external_document("ORGADATA", "QUOTING").canonical_entity == "technical_quotation"
    assert (
        resolve_external_document("ORGADATA", "FABRICATION").canonical_entity
        == "fabrication_sheet"
    )
    assert resolve_external_document("ORGADATA", "CUTTING").canonical_entity == "cutting_sheet"
    assert resolve_external_document("ORGADATA", "UNKNOWN") is None


def test_fabrication_and_cutting_have_distinct_business_meanings():
    fabrication = ENTITIES["fabrication_sheet"]
    cutting = ENTITIES["cutting_sheet"]

    assert fabrication.id != cutting.id
    assert "comment produire" not in cutting.definition.lower()
    assert "consommer" in cutting.definition.lower()
    assert "ouvrages" in fabrication.definition.lower()


def test_certifying_rules_lock_stock_and_production_order():
    gates = {gate.id: gate for gate in WORKFLOW_GATES}
    joined_rules = "\n".join(gate.rule for gate in WORKFLOW_GATES)

    assert "réservation active" in joined_rules.lower()
    assert "fabrication lancée" in joined_rules.lower()
    assert gates["reservation_requires_cutting_sheet"].required_entities == ("cutting_sheet",)
    assert gates["debit_requires_active_reservation"].required_entities == (
        "stock_reservation",
        "workshop_preparation",
        "production_order",
    )
    assert document_type_can_feed_stock("CUTTING") is True
    assert document_type_can_feed_stock("FABRICATION") is False


def test_modules_can_be_queried_for_ui_or_ai_context():
    payload = ontology_as_dict()
    crm_codes = {
        key for key, entity in payload["entities"].items() if entity["module"] == "CRM"
    }
    atelier_codes = {
        key
        for key, entity in payload["entities"].items()
        if entity["module"] in {"FABRICATION", "DEBIT"}
    }

    assert {"client", "contact", "crm_opportunity"}.issubset(crm_codes)
    assert {
        "industrial_dossier",
        "fabrication_sheet",
        "cutting_sheet",
        "production_order",
        "real_workshop_debit",
    }.issubset(atelier_codes)
    assert len(EXTERNAL_DOCUMENT_MAPPINGS) == 8
