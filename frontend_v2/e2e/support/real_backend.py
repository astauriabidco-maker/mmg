#!/usr/bin/env python3
"""Serveur FastAPI jetable pour la recette navigateur CRM/atelier.

La base SQLite, les uploads et toutes les données sont créés dans un dossier
temporaire supprimé à l'arrêt. Aucun document client réel n'est utilisé.
"""

from __future__ import annotations

import atexit
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_DIRECTORY = Path(tempfile.mkdtemp(prefix="mmg-crm-e2e-"))
DATABASE_PATH = RUNTIME_DIRECTORY / "crm-production.sqlite"
PORT = int(os.environ.get("MMG_E2E_BACKEND_PORT", "7100"))

sys.path.insert(0, str(REPOSITORY_ROOT))
os.chdir(RUNTIME_DIRECTORY)
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{DATABASE_PATH}"
os.environ["CRM_REMINDERS_ENABLED"] = "false"
os.environ["SECRET_KEY"] = "mmg-e2e-secret-key-not-for-production"
os.environ["CORS_ORIGINS"] = "http://127.0.0.1:5173"


def cleanup() -> None:
    shutil.rmtree(RUNTIME_DIRECTORY, ignore_errors=True)


atexit.register(cleanup)

from backend import database, models  # noqa: E402
from backend.core.security import get_password_hash  # noqa: E402
from backend.core.time import utcnow  # noqa: E402
from backend.seed_permissions import seed_permissions  # noqa: E402


def seed_browser_journey() -> None:
    models.Base.metadata.create_all(bind=database.engine)
    seed_permissions()
    db = database.SessionLocal()
    try:
        user = models.User(
            username="e2e_admin",
            first_name="Recette",
            last_name="Navigateur",
            pin_hash=get_password_hash("1234"),
            role="ADMIN",
            is_active=True,
            invitation_status="ACTIVE",
        )
        client = models.Client(
            name="CLIENT ANONYMISE E2E",
            contact_name="Contact Test",
            country="FR",
            customer_type="B2B",
            tags=[],
            is_active=True,
        )
        sale = models.SaleOrder(
            reference="DEVIS-E2E-0001",
            client_name=client.name,
            status="VALIDATED",
            workflow_type="FABRICATION_FROM_MEASURE",
            signed_at=utcnow(),
            author=user.username,
        )
        db.add_all([user, client, sale])
        db.flush()
        db.add(
            models.SaleOrderLine(
                order_id=sale.id,
                line_type="SERVICE",
                description="Menuiserie aluminium anonymisée",
                quantity=1,
                unit_price=1000,
                visual_config=json.dumps(
                    {
                        "width_mm": 1200,
                        "height_mm": 1400,
                        "material": "ALU",
                        "opening_type": "Fenêtre test",
                        "color_ral": "ANONYME",
                    }
                ),
            )
        )

        mission = models.MeasureMission(
            reference="MET-E2E-0001",
            client_id=client.id,
            sale_order_id=sale.id,
            status="VALIDATED",
            source_type="SITE_VISIT",
            project_scope="SUPPLY_AND_INSTALL",
            verification_status="READY_FOR_FABRICATION",
            purpose="Recette anonymisée du flux fabrication",
            scheduled_start=datetime(2026, 7, 29, 8, 0),
            scheduled_end=datetime(2026, 7, 29, 10, 0),
            created_by=user.username,
        )
        db.add(mission)
        db.flush()
        db.add(
            models.MeasureOpening(
                mission_id=mission.id,
                sequence=1,
                label="F01",
                room="Pièce test",
                product_type="WINDOW",
                width_mm=1200,
                height_mm=1400,
                material="ALU",
                status="VALIDATED",
            )
        )
        db.add(
            models.TechnicalDossier(
                reference="TECH-E2E-0001",
                mission_id=mission.id,
                quoting_status="VALIDATED",
                production_status="DRAFT",
                stock_status="LOCKED",
                launch_status="LOCKED",
                quoting_validated_at=utcnow(),
                quoting_validated_by=user.username,
                created_by=user.username,
            )
        )

        product = models.Product(
            reference_base="E2E-PROFILE",
            name="Profilé aluminium anonymisé",
            category="PROFIL",
            material_type="ALU",
            unit="barre",
            supplier="SEPALUMIC",
            product_type="stockable",
            catalog_status="ACTIVE",
        )
        db.add(product)
        db.flush()
        variant = models.ProductVariant(
            product_id=product.id,
            reference="E2E-PROFILE-001",
            supplier_reference="E2E-PROFILE-001",
            color="Anonyme",
            conditioning="barre",
            length_per_unit=6.5,
            quantity_in_stock=20,
        )
        stock_location = models.StockLocation(
            name="WH/Stock",
            usage="internal",
            is_active=True,
        )
        db.add_all([variant, stock_location])
        db.flush()
        db.add(
            models.StockQuant(
                variant_id=variant.id,
                location_id=stock_location.id,
                quantity=20,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


seed_browser_journey()

from backend.main import app  # noqa: E402
import uvicorn  # noqa: E402


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
