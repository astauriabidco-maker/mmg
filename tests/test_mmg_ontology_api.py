from backend import models
from backend.core import security
from backend.core.security import get_password_hash
from backend.core.time import utcnow


def _headers(session_factory, username="ontology-viewer"):
    with session_factory() as db:
        db.add(
            models.User(
                username=username,
                pin_hash=get_password_hash("4826"),
                role="MANAGER",
                is_active=True,
            )
        )
        db.commit()
    token = security.create_access_token(
        {
            "sub": username,
            "role": "MANAGER",
            "permissions": [],
        }
    )
    return {"Authorization": f"Bearer {token}"}


def test_mmg_ontology_api_requires_authentication(isolated_client):
    client, _ = isolated_client

    response = client.get("/v2/mmg/ontology")

    assert response.status_code == 401


def test_mmg_ontology_api_exposes_active_business_reference(isolated_client):
    client, session_factory = isolated_client

    response = client.get("/v2/mmg/ontology", headers=_headers(session_factory))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["pipeline"][0] == "client"
    assert payload["pipeline"][-1] == "real_workshop_debit"
    assert payload["entities"]["crm_opportunity"]["label"] == "Opportunité avant-vente"
    assert payload["model_bindings"]["stock_reservation"] == [
        "StockReservation",
        "StockReservationLine",
    ]
    assert "proposition_a_valider" in {
        item["code"] for item in payload["entity_statuses"]["crm_opportunity"]
    }
    assert "quote_signed" in {item["code"] for item in payload["business_events"]}
    assert {
        ("production_order", "launch", "SALES_EDIT"),
        ("real_workshop_debit", "consume", "workshop.consume_stock"),
    }.issubset(
        {
            (item["entity"], item["action"], item["permission"])
            for item in payload["step_rbac"]
        }
    )


def test_mmg_ontology_api_is_enriched_by_live_business_data(isolated_client):
    client, session_factory = isolated_client
    headers = _headers(session_factory, username="ontology-data-viewer")

    with session_factory() as db:
        required_permissions = [
            ("SALES_VIEW", "Ventes (CRM)", "Voir les devis et clients"),
            ("SALES_EDIT", "Ventes (CRM)", "Créer et modifier des devis"),
            ("workshop.reserve_stock", "Stock - Atelier", "Réserver le stock pour un débit atelier"),
            ("workshop.consume_stock", "Stock - Atelier", "Transformer une réservation atelier en débit réel"),
            ("stock.transfer", "Stock - Actions", "Transférer du stock entre emplacements"),
        ]
        for code, module, description in required_permissions:
            if not db.query(models.Permission).filter_by(code=code).first():
                db.add(
                    models.Permission(
                        code=code,
                        module=module,
                        description=description,
                    )
                )
        role = db.query(models.Role).filter_by(name="CHEF_STOCK").first()
        if not role:
            role = models.Role(name="CHEF_STOCK", description="Chef stock")
            db.add(role)
        db.flush()
        permissions = db.query(models.Permission).all()
        existing_role_permissions = {permission.code for permission in role.permissions}
        role.permissions.extend(
            permission
            for permission in permissions
            if permission.code not in existing_role_permissions
        )

        business_client = models.Client(name="Client Ontologie")
        db.add(business_client)
        db.flush()

        sale = models.SaleOrder(
            reference="DEV-ONTO-001",
            client_name=business_client.name,
            status="READY_FOR_PROD",
            signed_at=utcnow(),
        )
        db.add(sale)
        db.flush()

        opportunity = models.CRMOpportunity(
            reference="OPP-ONTO-001",
            client_id=business_client.id,
            sale_order_id=sale.id,
            title="Projet ontologie alimentée",
            stage="gagne",
        )
        mission = models.MeasureMission(
            reference="MET-ONTO-001",
            client_id=business_client.id,
            opportunity_id=opportunity.id,
            sale_order_id=sale.id,
            status="VALIDATED",
        )
        db.add_all([opportunity, mission])
        db.flush()

        dossier = models.TechnicalDossier(
            reference="DT-ONTO-001",
            mission_id=mission.id,
            production_status="VALIDATED",
            stock_status="VALIDATED",
            launch_status="VALIDATED",
        )
        db.add(dossier)
        db.flush()

        cutting = models.TechnicalDossierVersion(
            dossier_id=dossier.id,
            version_number=1,
            document_type="CUTTING",
            source_system="ORGADATA",
            original_filename="orgadata-cutting.txt",
            stored_filename="orgadata-cutting.txt",
            file_path="/uploads/test/orgadata-cutting.txt",
            checksum_sha256="a" * 64,
            analysis_status="PARSED",
            parsed_summary={},
            parsed_records=[],
            parsed_issues=[],
        )
        db.add(cutting)
        db.flush()

        reservation = models.StockReservation(
            reference="RSV-ONTO-001",
            sale_order_id=sale.id,
            technical_dossier_version_id=cutting.id,
            status="reserved",
        )
        db.add(reservation)
        db.commit()

    response = client.get("/v2/mmg/ontology", headers=headers)

    assert response.status_code == 200, response.text
    profile = response.json()["data_profile"]
    assert profile["entities"]["client"]["record_count"] >= 1
    assert profile["entities"]["crm_opportunity"]["status_counts"]["gagne"] == 1
    assert profile["entities"]["measure_mission"]["status_counts"]["VALIDATED"] == 1
    assert profile["entities"]["cutting_sheet"]["record_count"] == 1
    assert profile["entities"]["stock_reservation"]["status_counts"]["reserved"] == 1
    assert profile["external_documents"]["by_source_system"]["ORGADATA"] == 1
    assert profile["external_documents"]["by_document_type"]["CUTTING"] == 1
    assert profile["external_documents"]["observed_mappings"][0]["canonical_entity"] == "cutting_sheet"
    assert profile["rbac"]["missing_permissions"] == []
    assert "CHEF_STOCK" in profile["rbac"]["roles_by_permission"]["workshop.reserve_stock"]
