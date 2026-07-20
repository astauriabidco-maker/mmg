#!/usr/bin/env python3
"""Jeu de données de démonstration pour l'atelier MMG (base de développement).

Peuple la base ciblée par DATABASE_URL (défaut : sqlite:///./atelier.db) avec un
jeu réaliste et IDEMPOTENT : chaque entité est recherchée avant création, le
script peut donc être relancé sans créer de doublons. Un résumé est affiché en
fin d'exécution.

Usage :
    python scripts/seed_demo.py
    DATABASE_URL=sqlite:////tmp/atelier_demo.db python scripts/seed_demo.py

Mots de passe de démonstration (UNIQUEMENT pour le développement local,
configurables via variables d'environnement) :

    Compte       Rôle             Variable                     Défaut
    admin        ADMIN            DEMO_ADMIN_PASSWORD          Demo-Admin-2026!
    manager      MANAGER          DEMO_MANAGER_PASSWORD        Demo-Manager-2026!
    op_debit     DEBIT_OPERATOR   DEMO_OPERATOR_PASSWORD       Demo-Oper-2026!
    op_assembl.  OPERATOR         DEMO_OPERATOR_PASSWORD       Demo-Oper-2026!
    magasinier   STOREKEEPER      DEMO_STOREKEEPER_PASSWORD    Demo-Stock-2026!
    vendeur      SALES            DEMO_SALES_PASSWORD          Demo-Ventes-2026!
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal, engine  # noqa: E402
from backend import models  # noqa: E402
from backend.core.security import get_password_hash  # noqa: E402
from backend.seed_stations import ensure_default_stations  # noqa: E402

SUMMARY = {"created": [], "existing": []}


def report(verb, label, created):
    SUMMARY["created" if created else "existing"].append(f"{verb}: {label}")


def get_or_create(db, model, defaults=None, **lookup):
    """Retourne (instance, created) — recherche par les clés de lookup."""
    instance = db.query(model).filter_by(**lookup).first()
    if instance:
        return instance, False
    params = dict(lookup)
    params.update(defaults or {})
    instance = model(**params)
    db.add(instance)
    db.flush()
    return instance, True


def seed_roles(db):
    """Rôles de démonstration, dont STOREKEEPER (magasinier) avec droits stock."""
    for name, description in [
        ("ADMIN", "Administration opérationnelle"),
        ("MANAGER", "Pilotage atelier, ventes et stock"),
        ("SALES", "Avant-vente, CRM et devis"),
        ("OPERATOR", "Opérateur atelier"),
        ("DEBIT_OPERATOR", "Opérateur débit autorisé à consommer les réservations atelier"),
        ("STOREKEEPER", "Magasinier — gestion des stocks et réceptions"),
    ]:
        _, created = get_or_create(db, models.Role, name=name, defaults={"description": description})
        report("Rôle", name, created)

    permissions = {}
    for code, module, description in [
        ("STOCK_VIEW", "Stocks & Logistique", "Voir l'état des stocks"),
        ("STOCK_EDIT", "Stocks & Logistique", "Gérer les approvisionnements"),
    ]:
        perm, created = get_or_create(
            db, models.Permission, code=code,
            defaults={"module": module, "description": description},
        )
        report("Permission", code, created)
        permissions[code] = perm

    storekeeper = db.query(models.Role).filter_by(name="STOREKEEPER").first()
    for perm in permissions.values():
        if perm not in storekeeper.permissions:
            storekeeper.permissions.append(perm)
            report("Rôle", f"STOREKEEPER += {perm.code}", True)
    db.flush()


def seed_users(db):
    op_password = os.environ.get("DEMO_OPERATOR_PASSWORD", "Demo-Oper-2026!")
    users = [
        ("admin", "ADMIN", os.environ.get("DEMO_ADMIN_PASSWORD", "Demo-Admin-2026!"), "Admin", "Démo"),
        ("manager", "MANAGER", os.environ.get("DEMO_MANAGER_PASSWORD", "Demo-Manager-2026!"), "Martine", "Gérard"),
        ("op_debit", "DEBIT_OPERATOR", op_password, "Olivier", "Débit"),
        ("op_assemblage", "OPERATOR", op_password, "Awa", "Assemblage"),
        ("magasinier", "STOREKEEPER", os.environ.get("DEMO_STOREKEEPER_PASSWORD", "Demo-Stock-2026!"), "Moussa", "Stock"),
        ("vendeur", "SALES", os.environ.get("DEMO_SALES_PASSWORD", "Demo-Ventes-2026!"), "Valérie", "Ventes"),
    ]
    for username, role, password, first_name, last_name in users:
        _, created = get_or_create(
            db, models.User, username=username,
            defaults={
                "pin_hash": get_password_hash(password),
                "role": role,
                "first_name": first_name,
                "last_name": last_name,
                "is_active": True,
            },
        )
        report("Utilisateur", f"{username} ({role})", created)
    db.flush()


def seed_locations(db):
    """Emplacements racines du moteur de stock double-entrée."""
    locations = {}
    for usage, name in [
        ("supplier", "Fournisseurs (Virtuel)"),
        ("inventory", "Ajustement / Casse (Virtuel)"),
        ("production", "Production (Consommation)"),
        ("customer", "Clients (Livraison)"),
        ("internal", "Dépôt Principal"),
    ]:
        loc, created = get_or_create(db, models.StockLocation, usage=usage, defaults={"name": name})
        report("Emplacement", f"{loc.name} [{usage}]", created)
        locations[usage] = loc
    db.flush()
    return locations


def seed_partners(db):
    clients = [
        ("Société BâtiPlus", {"contact_name": "Paul Ndoumbe", "email": "contact@batiplus.cm",
                              "phone": "+237 690 11 22 33", "address": "Bonanjo, Douala",
                              "tax_id": "M012345678901A", "customer_type": "B2B"}),
        ("Hôtel Le Mangrove", {"contact_name": "Claire Etoa", "email": "achats@mangrove.cm",
                               "phone": "+237 699 44 55 66", "address": "Kribi, bord de mer",
                               "customer_type": "B2B"}),
        ("Mme Fotso Brigitte", {"contact_name": "Brigitte Fotso", "email": "b.fotso@example.com",
                                "phone": "+237 677 88 99 00", "address": "Bastos, Yaoundé",
                                "customer_type": "B2C"}),
    ]
    for name, defaults in clients:
        _, created = get_or_create(db, models.Client, name=name, defaults=defaults)
        report("Client", name, created)

    suppliers = [
        ("Profiléx Distribution", {
            "contact_name": "Jean Rigobert", "email": "ventes@profilex.cm",
            "phone": "+237 233 42 10 10", "address": "Zone industrielle, Douala",
            "country": "Cameroun", "supplier_category": "Profilés PVC/ALU",
            "default_currency": "XAF", "payment_terms": "30 jours fin de mois",
            "lead_time_days": 14, "delivery_terms": "Départ usine",
        }),
        ("VitroCam SARL", {
            "contact_name": "Sandrine Abena", "email": "commandes@vitrocam.cm",
            "phone": "+237 233 43 20 20", "address": "Bonabéri, Douala",
            "country": "Cameroun", "supplier_category": "Vitrages",
            "default_currency": "XAF", "payment_terms": "45 jours",
            "lead_time_days": 7, "incoterm": "DAP",
        }),
    ]
    for name, defaults in suppliers:
        _, created = get_or_create(db, models.Supplier, name=name, defaults=defaults)
        report("Fournisseur", name, created)
    db.flush()


def seed_catalog_and_stock(db, locations):
    """Catalogue produits, variantes, quants et mouvements d'entrée."""
    supplier_loc = locations["supplier"]
    internal_loc = locations["internal"]

    catalog = [
        # (reference_base, name, material_type, unit, [(ref variante, couleur, coût, qté initiale)])
        ("PVC-D70", "Dormant PVC 70 mm", "PVC", "ml",
         [("PVC-D70-BLANC", "Blanc", 4200.0, 120.0), ("PVC-D70-GRIS", "Gris 7016", 4600.0, 60.0)]),
        ("VIT-4164", "Double vitrage 4/16/4", "VITRAGE", "m2",
         [("VIT-4164-STD", "Standard", 28000.0, 25.0)]),
        ("QUIN-CRM", "Crémone oscillant-battant", "ACCESSOIRE", "pce",
         [("QUIN-CRM-STD", "Standard", 9500.0, 40.0)]),
        ("ALU-C60", "Cadre ALU série 60", "ALU", "ml",
         [("ALU-C60-ANOD", "Anodisé", 6800.0, 80.0)]),
    ]
    variants = {}
    for ref_base, name, material_type, unit, variant_defs in catalog:
        product, created = get_or_create(
            db, models.Product, reference_base=ref_base,
            defaults={"name": name, "material_type": material_type, "unit": unit,
                      "catalog_status": "ACTIVE"},
        )
        report("Produit", f"{ref_base} — {name}", created)
        for ref, color, cost, qty in variant_defs:
            variant, created = get_or_create(
                db, models.ProductVariant, reference=ref,
                defaults={"product_id": product.id, "color": color, "cost_price": cost,
                          "quantity_in_stock": qty, "min_threshold": 10.0},
            )
            report("Variante", ref, created)
            variants[ref] = (variant, qty)

    # Quants + mouvement d'entrée initial (double-entrée : fournisseur -> dépôt)
    for ref, (variant, qty) in variants.items():
        _, created = get_or_create(
            db, models.StockQuant, variant_id=variant.id, location_id=internal_loc.id,
            defaults={"quantity": qty},
        )
        report("Quant", f"{ref} x {qty} @ {internal_loc.name}", created)
        move_ref = f"WH/IN/DEMO-{ref}"
        _, created = get_or_create(
            db, models.StockMove, reference=move_ref,
            defaults={
                "variant_id": variant.id, "location_id": supplier_loc.id,
                "location_dest_id": internal_loc.id, "quantity": qty, "state": "done",
                "notes": "Stock initial de démonstration", "author": "seed_demo",
                "document_type": "SEED", "document_reference": move_ref,
            },
        )
        report("Mouvement", move_ref, created)
    db.flush()
    return variants


def seed_sales_flow(db, variants):
    """Devis signé -> ordre de fabrication -> livré -> facture payée."""
    vitrage, _ = variants["VIT-4164-STD"]
    devis, created = get_or_create(
        db, models.SaleOrder, reference="DEVIS-DEMO-0001",
        defaults={
            "client_name": "Mme Fotso Brigitte", "client_contact": "Brigitte Fotso",
            "client_email": "b.fotso@example.com", "client_address": "Bastos, Yaoundé",
            "status": "DELIVERED", "workflow_type": "FABRICATION_ESTIMATE",
            "tax_rate": 19.25, "currency": "XAF", "author": "vendeur",
            "signature_token": "demo-signature-token-0001",
            "signed_at": datetime.utcnow() - timedelta(days=12),
            "notes": "Devis de démonstration signé via le portail client.",
        },
    )
    report("Devis", "DEVIS-DEMO-0001 (signé, livré)", created)

    line_fab, created = get_or_create(
        db, models.SaleOrderLine, order_id=devis.id, description="Baie vitrée PVC 2 vantaux 1800x1500 — fabrication et pose",
        defaults={"line_type": "SERVICE", "quantity": 1.0, "unit_price": 485000.0},
    )
    report("Ligne devis", "fabrication baie PVC", created)
    _, created = get_or_create(
        db, models.SaleOrderLine, order_id=devis.id, description="Double vitrage 4/16/4 (fourniture)",
        defaults={"line_type": "STOCK_ITEM", "variant_id": vitrage.id,
                  "quantity": 5.4, "unit_price": 32000.0},
    )
    report("Ligne devis", "vitrage 4/16/4", created)

    order, created = get_or_create(
        db, models.Order, reference="CMD-DEMO-0001",
        defaults={
            "sale_order_id": devis.id, "sale_order_line_id": line_fab.id,
            "width": 1800.0, "height": 1500.0, "material": models.MaterialType.PVC,
            "client_name": "Mme Fotso Brigitte", "color": "Blanc", "quantity": 1,
            "system_type": "Baie 2 vantaux OB",
        },
    )
    report("Ordre de fabrication", "CMD-DEMO-0001", created)

    # Planning soldé sur les postes PVC (commande terminée)
    for station in ["PVC_DEBIT", "PVC_SOUDURE", "PVC_ASSEMBLAGE", "PVC_VITRAGE", "PVC_CONTROLE"]:
        _, created = get_or_create(
            db, models.Planning, order_id=order.id, station=station,
            defaults={"status": models.PlanningStatus.DONE, "priority": 0,
                      "assigned_to": "op_debit" if station == "PVC_DEBIT" else "op_assemblage"},
        )
        report("Planning", f"CMD-DEMO-0001 @ {station} (DONE)", created)

    subtotal = 485000.0 + 5.4 * 32000.0
    tax = round(subtotal * 0.1925, 2)
    invoice, created = get_or_create(
        db, models.Invoice, reference="FACT-DEMO-0001",
        defaults={
            "sale_order_id": devis.id, "client_name": "Mme Fotso Brigitte",
            "client_address": "Bastos, Yaoundé", "status": "PAID",
            "invoice_type": "FINAL", "due_date": datetime.utcnow() - timedelta(days=2),
            "subtotal": subtotal, "tax_rate": 19.25, "tax_amount": tax,
            "total": subtotal + tax,
        },
    )
    report("Facture", f"FACT-DEMO-0001 (payée, {subtotal + tax:,.0f} XAF TTC)", created)
    if created:
        db.add(models.InvoiceLine(invoice_id=invoice.id, unit_price=485000.0, quantity=1.0,
                                  tax_rate=19.25,
                                  description="Baie vitrée PVC 2 vantaux 1800x1500 — fabrication et pose"))
        db.add(models.InvoiceLine(invoice_id=invoice.id, unit_price=32000.0, quantity=5.4,
                                  tax_rate=19.25,
                                  description="Double vitrage 4/16/4 (fourniture)"))
        db.flush()
    _, created = get_or_create(
        db, models.Payment, invoice_id=invoice.id, method="VIREMENT",
        defaults={"amount": subtotal + tax, "reference": "VIR-DEMO-0001"},
    )
    report("Paiement", "VIR-DEMO-0001 (virement)", created)
    db.flush()
    return devis


def seed_purchase_flow(db, variants, locations):
    """Commande fournisseur réceptionnée + mouvements d'entrée associés."""
    dormant, _ = variants["PVC-D70-BLANC"]
    cremone, _ = variants["QUIN-CRM-STD"]
    po, created = get_or_create(
        db, models.PurchaseOrder, reference="PO-DEMO-0001",
        defaults={
            "supplier": "Profiléx Distribution", "status": models.PurchaseOrderStatus.RECEIVED,
            "expected_date": datetime.utcnow() - timedelta(days=20),
            "total_amount": 120 * 4200.0 + 40 * 9500.0, "author": "magasinier",
            "notes": "Commande fournisseur de démonstration (réceptionnée).",
        },
    )
    report("Commande fournisseur", "PO-DEMO-0001 (réceptionnée)", created)

    for variant, qty, price in [(dormant, 120.0, 4200.0), (cremone, 40.0, 9500.0)]:
        _, created = get_or_create(
            db, models.PurchaseOrderLine, order_id=po.id, variant_id=variant.id,
            defaults={"quantity": qty, "quantity_received": qty, "unit_price": price},
        )
        report("Ligne achat", f"{variant.reference} x {qty} (reçue)", created)
    db.flush()


def seed_mmg(db, devis):
    """Dossier MMG (métré menuiserie) validé, rattaché au devis de démo."""
    _, created = get_or_create(
        db, models.MMG, reference="MMG-DEMO-0001",
        defaults={
            "client_name": "Mme Fotso Brigitte", "client_contact": "+237 677 88 99 00",
            "client_address": "Bastos, Yaoundé", "site_address": "Bastos, Yaoundé — Villa 12",
            "client_email": "b.fotso@example.com", "client_type": "PARTICULIER",
            "width": 1800.0, "height": 1500.0, "passage_height": 1300.0,
            "opening_type": "tirant", "opening_side": "gauche", "sash_count": 2,
            "view_type": "interior", "material": "PVC", "product_series": "Standard",
            "color_ral": "RAL 9016", "glazing_type": "4/16/4",
            "installation_type": "Reno", "hardware_type": "Standard",
            "floor_number": 0, "environment": "Standard",
            "photos": "", "signature": "",
            "status": models.MMGStatus.VALIDATED,
            "sale_order_id": devis.id,
            "quote_sent_at": datetime.utcnow() - timedelta(days=14),
        },
    )
    report("Dossier MMG", "MMG-DEMO-0001 (validé)", created)
    db.flush()


def ensure_drift_columns():
    """Corrige les dérives de schéma de la base de développement.

    La base dev historique a été créée via create_all() sans suivi Alembic
    (table alembic_version vide) : `alembic upgrade head` ne peut donc pas la
    rattraper. Comme models.ensure_schema_compatibility(), on ajoute ici les
    colonnes manquantes (ADD COLUMN uniquement, colonnes nullables) pour les
    tables existantes, sans jamais altérer les données.
    """
    from sqlalchemy import inspect, text

    added = []
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table in models.Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing or not column.nullable:
                    continue
                column_type = column.type.compile(dialect=connection.dialect)
                connection.execute(
                    text(f'ALTER TABLE {table.name} ADD COLUMN {column.name} {column_type}')
                )
                added.append(f"{table.name}.{column.name}")
    if added:
        print(f"Dérive de schéma corrigée ({len(added)} colonnes ajoutées) : "
              + ", ".join(added))


def main():
    # Le schéma est géré par Alembic (`alembic upgrade head`, notamment la
    # migration de rattrapage e5c9f2a8d417) — voir scripts/reset_dev_db.sh.
    # create_all + ensure_drift_columns restent un filet de sécurité pour les
    # bases dev historiques non resynchronisées.
    models.Base.metadata.create_all(bind=engine)
    ensure_drift_columns()
    ensure_default_stations()

    db = SessionLocal()
    try:
        seed_roles(db)
        seed_users(db)
        locations = seed_locations(db)
        seed_partners(db)
        variants = seed_catalog_and_stock(db, locations)
        devis = seed_sales_flow(db, variants)
        seed_purchase_flow(db, variants, locations)
        seed_mmg(db, devis)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print("\n=== Jeu de données de démonstration ===")
    print(f"Créés ({len(SUMMARY['created'])}) :")
    for item in SUMMARY["created"]:
        print(f"  + {item}")
    print(f"Déjà présents ({len(SUMMARY['existing'])}) :")
    for item in SUMMARY["existing"]:
        print(f"  = {item}")
    print("\nTerminé. Comptes de démonstration : admin / manager / op_debit / "
          "op_assemblage / magasinier / vendeur (mots de passe : variables "
          "DEMO_*_PASSWORD, voir l'en-tête du script).")


if __name__ == "__main__":
    main()
