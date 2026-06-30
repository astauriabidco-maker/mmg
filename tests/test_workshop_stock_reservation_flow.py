import io
import json

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import database, models
from backend.core import security
from backend.main import app


def test_workshop_debit_reservation_is_consumed_only_when_confirmed():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = override_get_db

    try:
        with TestingSessionLocal() as db:
            product = models.Product(
                reference_base="SEPALUMIC:7007",
                name="Bavette de faitage",
                material_type="ALU",
                unit="barre",
                supplier="SEPALUMIC",
                product_type="stockable",
            )
            db.add(product)
            db.flush()
            variant = models.ProductVariant(
                product_id=product.id,
                reference="SEPALUMIC:7007",
                supplier_reference="7007",
                quantity_in_stock=5,
                min_threshold=0,
            )
            location = models.StockLocation(name="WH/Stock", usage="internal", is_active=True)
            db.add_all([variant, location])
            db.flush()
            db.add(models.StockQuant(variant_id=variant.id, location_id=location.id, quantity=5))
            sale = models.SaleOrder(
                reference="DEV-ATELIER-1",
                client_name="Client atelier",
                status="IN_DESIGN",
                tax_rate=20,
            )
            db.add(sale)
            db.flush()
            db.add(
                models.SaleOrderLine(
                    order_id=sale.id,
                    description="Menuiserie ALU Sepalumic",
                    quantity=1,
                    unit_price=1000,
                )
            )
            db.commit()
            sale_id = sale.id

        client = TestClient(app)
        token = security.create_access_token({"sub": "atelier-manager", "role": "ADMIN"})
        headers = {"Authorization": f"Bearer {token}"}
        content = b"SEPALUMIC GAMME BASE\r\nVER TEST\r\nRAL;7007;BAVETTE DE FAITAGE;3;barre  6,50\r\n"

        preview_response = client.post(
            "/v2/stock/workshop-debits/preview",
            headers=headers,
            data={"sale_order_id": str(sale_id)},
            files=[("files", ("SEPVER.TXT", content, "text/plain"))],
        )
        assert preview_response.status_code == 200, preview_response.text
        assert preview_response.json()["summary"]["stock_match_status"] == {"ok": 1}
        assert preview_response.json()["issues"] == []

        reserve_response = client.post(
            "/v2/stock/workshop-debits/reservations",
            headers=headers,
            data={"sale_order_id": str(sale_id)},
            files=[("files", ("SEPVER.TXT", content, "text/plain"))],
        )
        assert reserve_response.status_code == 200, reserve_response.text
        reservation = reserve_response.json()
        assert reservation["status"] == "reserved"
        assert reservation["sale_order_id"] == sale_id
        assert reservation["lines"][0]["reserved_quantity"] == 3

        with TestingSessionLocal() as db:
            quant = db.query(models.StockQuant).one()
            variant = db.query(models.ProductVariant).one()
            assert quant.quantity == 5
            assert variant.quantity_in_stock == 5

        consume_response = client.post(
            f"/v2/stock/workshop-debits/reservations/{reservation['id']}/consume",
            headers=headers,
        )
        assert consume_response.status_code == 200, consume_response.text
        assert consume_response.json()["created_moves"] == 1

        with TestingSessionLocal() as db:
            source_quant = db.query(models.StockQuant).join(models.StockLocation).filter(models.StockLocation.name == "WH/Stock").one()
            dest_quant = (
                db.query(models.StockQuant)
                .join(models.StockLocation)
                .filter(models.StockLocation.name == "Production Ateliers")
                .one()
            )
            variant = db.query(models.ProductVariant).one()
            move = db.query(models.StockMove).one()
            reservation_db = db.query(models.StockReservation).one()

        assert source_quant.quantity == 2
        assert dest_quant.quantity == 3
        assert variant.quantity_in_stock == 2
        assert move.quantity == 3
        assert move.reference.startswith("DEBIT-ATELIER-")
        assert "Débit atelier réel" in move.notes
        assert "DEV-ATELIER-1" in move.notes
        assert reservation_db.status == "consumed"
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_workshop_debit_reservation_can_be_cancelled_without_stock_move():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = override_get_db

    try:
        with TestingSessionLocal() as db:
            product = models.Product(
                reference_base="SEPALUMIC:7007",
                name="Bavette de faitage",
                material_type="ALU",
                unit="barre",
                supplier="SEPALUMIC",
                product_type="stockable",
            )
            db.add(product)
            db.flush()
            variant = models.ProductVariant(
                product_id=product.id,
                reference="SEPALUMIC:7007",
                supplier_reference="7007",
                quantity_in_stock=5,
                min_threshold=0,
            )
            location = models.StockLocation(name="WH/Stock", usage="internal", is_active=True)
            db.add_all([variant, location])
            db.flush()
            db.add(models.StockQuant(variant_id=variant.id, location_id=location.id, quantity=5))
            sale = models.SaleOrder(
                reference="DEV-ATELIER-CANCEL",
                client_name="Client atelier",
                status="VALIDATED",
                tax_rate=20,
            )
            db.add(sale)
            db.flush()
            db.add(
                models.SaleOrderLine(
                    order_id=sale.id,
                    description="Menuiserie ALU Sepalumic",
                    quantity=1,
                    unit_price=1000,
                )
            )
            db.commit()
            sale_id = sale.id

        client = TestClient(app)
        token = security.create_access_token({"sub": "atelier-manager", "role": "ADMIN"})
        headers = {"Authorization": f"Bearer {token}"}
        content = b"SEPALUMIC GAMME BASE\r\nVER TEST\r\nRAL;7007;BAVETTE DE FAITAGE;3;barre  6,50\r\n"

        reserve_response = client.post(
            "/v2/stock/workshop-debits/reservations",
            headers=headers,
            data={"sale_order_id": str(sale_id)},
            files=[("files", ("SEPVER.TXT", content, "text/plain"))],
        )
        assert reserve_response.status_code == 200, reserve_response.text
        reservation = reserve_response.json()

        cancel_response = client.post(
            f"/v2/stock/workshop-debits/reservations/{reservation['id']}/cancel",
            headers=headers,
        )
        assert cancel_response.status_code == 200, cancel_response.text
        assert cancel_response.json()["cancelled_lines"] == 1
        assert cancel_response.json()["released_quantity"] == 3

        with TestingSessionLocal() as db:
            quant = db.query(models.StockQuant).one()
            variant = db.query(models.ProductVariant).one()
            reservation_db = db.query(models.StockReservation).one()
            line = db.query(models.StockReservationLine).one()
            moves = db.query(models.StockMove).count()

        assert quant.quantity == 5
        assert variant.quantity_in_stock == 5
        assert reservation_db.status == "cancelled"
        assert line.status == "cancelled"
        assert moves == 0
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_sale_workshop_preparation_reserves_stock_without_physical_debit():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = override_get_db

    try:
        with TestingSessionLocal() as db:
            product = models.Product(
                reference_base="CORTIZO:2000",
                name="Profil Cortizo 2000",
                material_type="ALU",
                unit="barre",
                supplier="CORTIZO",
                product_type="stockable",
            )
            db.add(product)
            db.flush()
            variant = models.ProductVariant(
                product_id=product.id,
                reference="CORTIZO:2000",
                supplier_reference="2000",
                quantity_in_stock=5,
                min_threshold=0,
            )
            location = models.StockLocation(name="WH/Stock", usage="internal", is_active=True)
            db.add_all([variant, location])
            db.flush()
            db.add(models.StockQuant(variant_id=variant.id, location_id=location.id, quantity=5))
            sale = models.SaleOrder(
                reference="DEV-PREP-ATELIER",
                client_name="Client préparation",
                status="VALIDATED",
                tax_rate=20,
            )
            db.add(sale)
            db.flush()
            db.add(
                models.SaleOrderLine(
                    order_id=sale.id,
                    description="Menuiserie ALU Cortizo",
                    quantity=1,
                    unit_price=1000,
                )
            )
            db.commit()
            sale_id = sale.id

        client = TestClient(app)
        token = security.create_access_token({"sub": "sales-manager", "role": "ADMIN"})
        headers = {"Authorization": f"Bearer {token}"}
        content = b"CORTIZO GAMME BASE\r\nVER TEST\r\nRAL;2000;PROFIL;4;barre  6,50\r\n"

        preview_response = client.post(
            f"/v2/sales/{sale_id}/prepare-workshop/preview",
            headers=headers,
            files=[("files", ("SEPVER.TXT", content, "text/plain"))],
        )
        assert preview_response.status_code == 200, preview_response.text
        assert preview_response.json()["summary"]["stock_match_status"] == {"ok": 1}

        reserve_response = client.post(
            f"/v2/sales/{sale_id}/prepare-workshop/reserve",
            headers=headers,
            files=[("files", ("SEPVER.TXT", content, "text/plain"))],
        )
        assert reserve_response.status_code == 200, reserve_response.text
        assert reserve_response.json()["status"] == "READY_FOR_PROD"
        assert reserve_response.json()["reserved_lines"] == 1

        with TestingSessionLocal() as db:
            sale_db = db.query(models.SaleOrder).one()
            reservation = db.query(models.StockReservation).one()
            quant = db.query(models.StockQuant).one()
            variant = db.query(models.ProductVariant).one()
            moves = db.query(models.StockMove).count()

        assert sale_db.status == "READY_FOR_PROD"
        assert reservation.sale_order_id == sale_id
        assert reservation.status == "reserved"
        assert quant.quantity == 5
        assert variant.quantity_in_stock == 5
        assert moves == 0
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_launch_production_is_idempotent_and_links_reservation_to_order():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = override_get_db

    try:
        with TestingSessionLocal() as db:
            sale = models.SaleOrder(
                reference="DEV-LAUNCH-ATELIER",
                client_name="Client lancement",
                status="READY_FOR_PROD",
                tax_rate=20,
            )
            db.add(sale)
            db.flush()
            line = models.SaleOrderLine(
                order_id=sale.id,
                description="Chassis ALU Cortizo",
                quantity=2,
                unit_price=1000,
                visual_config=json.dumps(
                    {
                        "type": "Coulissant 2 vantaux",
                        "width": 1800,
                        "height": 2150,
                        "material": "ALU",
                        "color": "RAL 7016",
                    }
                ),
            )
            db.add(line)
            reservation = models.StockReservation(
                reference="RSV-LAUNCH-1",
                sale_order_id=sale.id,
                status="reserved",
                source_label="SEPVER.TXT",
                created_by="test",
            )
            db.add(reservation)
            db.commit()
            sale_id = sale.id
            line_id = line.id

        client = TestClient(app)
        token = security.create_access_token({"sub": "sales-manager", "role": "ADMIN"})
        headers = {"Authorization": f"Bearer {token}"}

        first_response = client.post(f"/v2/sales/{sale_id}/launch-production", headers=headers)
        assert first_response.status_code == 200, first_response.text
        assert first_response.json()["created_orders"] == 1
        assert first_response.json()["linked_reservations"] == 1

        second_response = client.post(f"/v2/sales/{sale_id}/launch-production", headers=headers)
        assert second_response.status_code == 200, second_response.text
        assert second_response.json()["created_orders"] == 0
        assert second_response.json()["existing_orders"] == 1

        with TestingSessionLocal() as db:
            sale_db = db.query(models.SaleOrder).one()
            order = db.query(models.Order).one()
            plans = db.query(models.Planning).all()
            reservation_db = db.query(models.StockReservation).one()

        assert sale_db.status == "IN_PRODUCTION"
        assert order.sale_order_id == sale_id
        assert order.sale_order_line_id == line_id
        assert order.width == 1800
        assert order.height == 2150
        assert order.quantity == 2
        assert order.reference.startswith("PROD-LAUNCH-ATELIER-L")
        assert len(plans) == 1
        assert reservation_db.production_order_id == order.id
        assert reservation_db.order_reference == order.reference
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_workshop_reservation_requires_validated_and_coherent_sale_order():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = override_get_db

    try:
        with TestingSessionLocal() as db:
            draft = models.SaleOrder(reference="DEV-DRAFT", client_name="Draft", status="DRAFT", tax_rate=20)
            pvc = models.SaleOrder(reference="DEV-PVC", client_name="PVC", status="VALIDATED", tax_rate=20)
            db.add_all([draft, pvc])
            db.flush()
            db.add_all(
                [
                    models.SaleOrderLine(order_id=draft.id, description="Menuiserie ALU", quantity=1, unit_price=1000),
                    models.SaleOrderLine(order_id=pvc.id, description="Fenêtre PVC", quantity=1, unit_price=1000),
                ]
            )
            db.commit()
            draft_id = draft.id
            pvc_id = pvc.id

        client = TestClient(app)
        token = security.create_access_token({"sub": "atelier-manager", "role": "ADMIN"})
        headers = {"Authorization": f"Bearer {token}"}
        content = b"SEPALUMIC GAMME BASE\r\nVER TEST\r\nRAL;7007;BAVETTE DE FAITAGE;3;barre  6,50\r\n"

        draft_response = client.post(
            "/v2/stock/workshop-debits/reservations",
            headers=headers,
            data={"sale_order_id": str(draft_id), "allow_missing": "true"},
            files=[("files", ("SEPVER.TXT", content, "text/plain"))],
        )
        assert draft_response.status_code == 400
        assert "réservation autorisée seulement après validation" in draft_response.text

        mismatch_response = client.post(
            "/v2/stock/workshop-debits/reservations",
            headers=headers,
            data={"sale_order_id": str(pvc_id), "allow_missing": "true"},
            files=[("files", ("SEPVER.TXT", content, "text/plain"))],
        )
        assert mismatch_response.status_code == 400
        assert "Incohérence matière" in mismatch_response.text
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_workshop_debit_contexts_include_active_production_orders_without_sales():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = override_get_db

    try:
        with TestingSessionLocal() as db:
            order = models.Order(
                reference="CMD-ATELIER-1",
                width=1200,
                height=900,
                material=models.MaterialType.ALU,
                client_name="Client atelier",
                quantity=1,
            )
            db.add(order)
            db.flush()
            db.add(
                models.Planning(
                    order_id=order.id,
                    station="ALU_DEBIT",
                    status=models.PlanningStatus.PENDING,
                )
            )
            db.commit()

        client = TestClient(app)
        token = security.create_access_token({"sub": "atelier-manager", "role": "ADMIN"})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v2/stock/workshop-debits/contexts", headers=headers)

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["sales"] == []
        assert payload["production_orders"] == [
            {
                "type": "production_order",
                "id": 1,
                "reference": "CMD-ATELIER-1",
                "client_name": "Client atelier",
                "status": "PENDING",
                "material": "ALU",
                "station": "ALU_DEBIT",
                "label": "CMD-ATELIER-1 - Client atelier (ALU)",
            }
        ]
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_workshop_debit_preview_is_allowed_without_context_but_flags_workflow():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = override_get_db

    try:
        client = TestClient(app)
        token = security.create_access_token({"sub": "atelier-manager", "role": "ADMIN"})
        headers = {"Authorization": f"Bearer {token}"}
        content = b"SEPALUMIC GAMME BASE\r\nVER TEST\r\nRAL;7007;BAVETTE DE FAITAGE;3;barre  6,50\r\n"

        response = client.post(
            "/v2/stock/workshop-debits/preview",
            headers=headers,
            files=[("files", ("SEPVER.TXT", content, "text/plain"))],
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["summary"]["debit_lines"] == 1
        assert any(issue["code"] == "missing_workflow_context" for issue in payload["issues"])
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_workshop_unknown_lines_can_create_zero_stock_draft_products():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = override_get_db

    try:
        client = TestClient(app)
        token = security.create_access_token({"sub": "atelier-manager", "role": "ADMIN"})
        headers = {"Authorization": f"Bearer {token}"}
        content = b"SEPALUMIC GAMME BASE\r\nVER TEST\r\nRAL;7007;BAVETTE DE FAITAGE;3;barre  6,50\r\n"

        create_response = client.post(
            "/v2/stock/workshop-debits/draft-products",
            headers=headers,
            files=[("files", ("SEPVER.TXT", content, "text/plain"))],
        )

        assert create_response.status_code == 200, create_response.text
        assert create_response.json()["created"] == 1
        assert create_response.json()["references"] == ["SEPALUMIC:7007"]

        preview_response = client.post(
            "/v2/stock/workshop-debits/preview",
            headers=headers,
            files=[("files", ("SEPVER.TXT", content, "text/plain"))],
        )

        assert preview_response.status_code == 200, preview_response.text
        payload = preview_response.json()
        assert payload["summary"]["stock_match_status"] == {"shortage": 1}

        with TestingSessionLocal() as db:
            product = db.query(models.Product).one()
            variant = db.query(models.ProductVariant).one()
            quant = db.query(models.StockQuant).one()

        assert product.name.startswith("[BROUILLON]")
        assert product.supplier == "SEPALUMIC"
        assert product.material_type == "ALU"
        assert product.catalog_status == "DRAFT"
        assert variant.reference == "SEPALUMIC:7007"
        assert variant.supplier_reference == "7007"
        assert variant.quantity_in_stock == 0
        assert quant.quantity == 0
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_draft_catalog_can_be_exported_and_reimported():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = override_get_db

    try:
        client = TestClient(app)
        token = security.create_access_token({"sub": "atelier-manager", "role": "ADMIN"})
        headers = {"Authorization": f"Bearer {token}"}
        content = b"SEPALUMIC GAMME BASE\r\nVER TEST\r\nRAL;7007;BAVETTE DE FAITAGE;3;barre  6,50\r\n"

        create_response = client.post(
            "/v2/stock/workshop-debits/draft-products",
            headers=headers,
            files=[("files", ("SEPVER.TXT", content, "text/plain"))],
        )
        assert create_response.status_code == 200, create_response.text

        export_response = client.get("/v2/stock/catalog/drafts/export", headers=headers)
        assert export_response.status_code == 200, export_response.text

        workbook = load_workbook(io.BytesIO(export_response.content))
        sheet = workbook.active
        headers_row = [cell.value for cell in sheet[1]]
        values = {header: index + 1 for index, header in enumerate(headers_row)}
        sheet.cell(row=2, column=values["Nom_Famille"]).value = "Profil SEPALUMIC 7007 - Bavette de faitage"
        sheet.cell(row=2, column=values["Longueur_Unite"]).value = 6500
        sheet.cell(row=2, column=values["Emplacement"]).value = "Rack ALU A1"
        sheet.cell(row=2, column=values["Statut_Catalogue"]).value = "ACTIVE"
        buffer = io.BytesIO()
        workbook.save(buffer)
        buffer.seek(0)

        import_response = client.post(
            "/v2/stock/catalog/drafts/import",
            headers=headers,
            files=[("file", ("drafts.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))],
        )
        assert import_response.status_code == 200, import_response.text
        assert import_response.json()["updated_products"] == 1
        assert import_response.json()["updated_variants"] == 1

        with TestingSessionLocal() as db:
            product = db.query(models.Product).one()
            variant = db.query(models.ProductVariant).one()

        assert product.name == "Profil SEPALUMIC 7007 - Bavette de faitage"
        assert product.catalog_status == "ACTIVE"
        assert variant.length_per_unit == 6500
        assert variant.location == "Rack ALU A1"
        assert variant.quantity_in_stock == 0
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)
