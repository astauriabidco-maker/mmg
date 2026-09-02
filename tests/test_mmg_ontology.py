from backend.domain.ontology import (
    BUSINESS_EVENTS,
    DOCUMENT_TYPES,
    ENTITIES,
    ENTITY_STATUSES,
    EXTERNAL_DOCUMENT_MAPPINGS,
    MODEL_BINDINGS,
    PIPELINE,
    RELATIONS,
    STEP_RBAC,
    WORKFLOW_GATES,
    document_type_can_feed_stock,
    ontology_as_dict,
    resolve_external_document,
    validate_ontology,
)


def test_ontology_is_structurally_consistent():
    assert validate_ontology() == []


def test_pipeline_links_crm_to_real_workshop_debit():
    assert PIPELINE[0] == "client"
    assert PIPELINE[-1] == "real_workshop_debit"

    relation_pairs = {(relation.source, relation.target) for relation in RELATIONS}
    expected_pairs = {
        ("client", "crm_opportunity"),
        ("crm_opportunity", "measure_mission"),
        ("measure_mission", "technical_dossier"),
        ("technical_dossier", "technical_quotation"),
        ("technical_quotation", "commercial_quote"),
        ("commercial_quote", "signed_order"),
        ("signed_order", "industrial_dossier"),
        ("industrial_dossier", "fabrication_sheet"),
        ("industrial_dossier", "cutting_sheet"),
        ("cutting_sheet", "stock_reservation"),
        ("stock_reservation", "workshop_preparation"),
        ("signed_order", "production_order"),
        ("production_order", "real_workshop_debit"),
    }
    assert expected_pairs.issubset(relation_pairs)


def test_proges_orgadata_documents_resolve_to_distinct_canonical_objects():
    assert resolve_external_document("PROGES", "QUOTING").canonical_entity == "technical_quotation"
    assert resolve_external_document("PROGES", "FABRICATION").canonical_entity == "fabrication_sheet"
    assert resolve_external_document("PROGES", "CUTTING").canonical_entity == "cutting_sheet"
    assert resolve_external_document("PROGES", "VALUATION").canonical_entity == "technical_quotation"
    assert resolve_external_document("ORGADATA", "QUOTING").canonical_entity == "technical_quotation"
    assert resolve_external_document("ORGADATA", "FABRICATION").canonical_entity == "fabrication_sheet"
    assert resolve_external_document("ORGADATA", "CUTTING").canonical_entity == "cutting_sheet"
    assert resolve_external_document("ORGADATA", "VALUATION").canonical_entity == "technical_quotation"

    assert resolve_external_document("ORGADATA", "FABRICATION").canonical_entity != (
        resolve_external_document("ORGADATA", "CUTTING").canonical_entity
    )


def test_external_document_mappings_prevent_known_confusions():
    mapping_by_source_and_type = {
        (mapping.source_system, mapping.document_type): mapping
        for mapping in EXTERNAL_DOCUMENT_MAPPINGS
    }

    assert "commercial_quote" in mapping_by_source_and_type[
        ("PROGES", "QUOTING")
    ].forbidden_confusions
    assert "fabrication_sheet" in mapping_by_source_and_type[
        ("ORGADATA", "CUTTING")
    ].forbidden_confusions
    assert "cutting_sheet" in mapping_by_source_and_type[
        ("ORGADATA", "FABRICATION")
    ].forbidden_confusions
    assert "real_workshop_debit" in mapping_by_source_and_type[
        ("PROGES", "CUTTING")
    ].forbidden_confusions


def test_workflow_gates_capture_critical_business_rules():
    gates = {gate.id: gate for gate in WORKFLOW_GATES}

    assert gates["production_requires_signed_order"].required_entities == (
        "signed_order",
        "fabrication_sheet",
        "cutting_sheet",
    )
    assert gates["reservation_requires_cutting_sheet"].required_entities == (
        "cutting_sheet",
    )
    assert gates["debit_requires_active_reservation"].required_entities == (
        "stock_reservation",
        "workshop_preparation",
        "production_order",
    )


def test_only_cutting_documents_can_feed_stock():
    assert document_type_can_feed_stock("CUTTING") is True
    assert document_type_can_feed_stock("FABRICATION") is False
    assert document_type_can_feed_stock("QUOTING") is False
    assert document_type_can_feed_stock("VALUATION") is False
    assert DOCUMENT_TYPES["CUTTING"]["stock_source"] is True


def test_ontology_serializes_for_api_or_rag_usage():
    payload = ontology_as_dict()

    assert payload["entities"]["crm_opportunity"]["label"] == "Opportunité avant-vente"
    assert payload["entities"]["cutting_sheet"]["module"] == "DEBIT"
    assert "Fiche fabrication" in ENTITIES["fabrication_sheet"].label
    assert payload["workflow_gates"]
    assert payload["entity_statuses"]["crm_opportunity"]
    assert payload["business_events"]
    assert payload["step_rbac"]
    assert payload["model_bindings"]["crm_opportunity"] == ("CRMOpportunity",)


def test_ontology_declares_sqlalchemy_model_bindings():
    assert MODEL_BINDINGS["client"] == ("Client",)
    assert MODEL_BINDINGS["contact"] == ("ClientContact",)
    assert "TechnicalDossierVersion" in MODEL_BINDINGS["cutting_sheet"]
    assert "StockReservation" in MODEL_BINDINGS["stock_reservation"]
    assert "StockMove" in MODEL_BINDINGS["real_workshop_debit"]


def test_ontology_declares_detailed_statuses_by_entity():
    opportunity_status_codes = {
        status.code for status in ENTITY_STATUSES["crm_opportunity"]
    }
    reservation_status_codes = {
        status.code for status in ENTITY_STATUSES["stock_reservation"]
    }

    assert "proposition_a_valider" in opportunity_status_codes
    assert "gagne" in opportunity_status_codes
    assert "ACTIVE" in reservation_status_codes
    assert "CONSUMED" in reservation_status_codes
    assert any(status.final for status in ENTITY_STATUSES["commercial_quote"])


def test_ontology_declares_business_events():
    event_codes = {event.code for event in BUSINESS_EVENTS}

    assert {
        "quote_sent",
        "quote_signed",
        "technical_dossier_validated",
        "stock_reserved",
        "production_launched",
        "stock_consumed",
    }.issubset(event_codes)


def test_ontology_declares_step_rbac_rules():
    permissions_by_entity_action = {
        (item.entity, item.action): item.permission for item in STEP_RBAC
    }

    assert permissions_by_entity_action[("crm_opportunity", "write")] == "SALES_EDIT"
    assert permissions_by_entity_action[("technical_dossier", "review")] == "PRODUCTION_MANAGE"
    assert permissions_by_entity_action[("stock_reservation", "write")] == "STOCK_MANAGE"
    assert permissions_by_entity_action[("production_order", "launch")] == "PRODUCTION_MANAGE"
    assert permissions_by_entity_action[("real_workshop_debit", "consume")] == "STOCK_MANAGE"
