from backend.domain.ontology import (
    DOCUMENT_TYPES,
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
