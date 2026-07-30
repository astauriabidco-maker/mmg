from backend import models
from backend.core import security
from backend.routers.v2_mmg import BE_REVIEW_ROLES
from backend import seed_permissions as seed_permissions_module


def _seed_access(session_factory, username: str, role_name: str, permission_codes: list[str]) -> dict:
    with session_factory() as db:
        permissions = []
        for code in permission_codes:
            permission = db.query(models.Permission).filter_by(code=code).first()
            if not permission:
                permission = models.Permission(
                    code=code,
                    module="Tests",
                    description=f"Permission test {code}",
                )
                db.add(permission)
                db.flush()
            permissions.append(permission)

        role = db.query(models.Role).filter_by(name=role_name).first()
        if not role:
            role = models.Role(name=role_name, description=f"Rôle test {role_name}")
            db.add(role)
        role.permissions = permissions

        user = db.query(models.User).filter_by(username=username).first()
        if not user:
            user = models.User(
                username=username,
                pin_hash="test-pin",
                role=role_name,
                is_active=True,
            )
            db.add(user)
        db.commit()

    token = security.create_access_token({"sub": username, "role": role_name})
    return {"Authorization": f"Bearer {token}"}


def _invoice_payload() -> dict:
    return {
        "client_name": "Client Finance",
        "client_address": "1 rue des Tests",
        "client_siret": "12345678900012",
        "due_date": "2026-08-31T00:00:00",
        "lines": [
            {
                "description": "Prestation test",
                "quantity": 1,
                "unit_price": 100,
                "tax_rate": 20,
            }
        ],
    }


def test_cross_functional_roles_are_seeded_with_expected_scope(isolated_client, monkeypatch):
    _, session_factory = isolated_client
    monkeypatch.setattr(seed_permissions_module, "SessionLocal", session_factory)

    seed_permissions_module.seed_permissions()

    with session_factory() as db:
        technico = db.query(models.Role).filter_by(name="TECHNICO_COMMERCIAL").one()
        finance = db.query(models.Role).filter_by(name="FINANCE").one()
        manager = db.query(models.Role).filter_by(name="MANAGER").one()

        technico_permissions = {permission.code for permission in technico.permissions}
        finance_permissions = {permission.code for permission in finance.permissions}
        manager_permissions = {permission.code for permission in manager.permissions}

    assert {
        "SALES_VIEW",
        "SALES_EDIT",
        "STOCK_VIEW",
        "workshop.reserve_stock",
        "PLANNING_VIEW",
        "PLANNING_EDIT",
    }.issubset(technico_permissions)
    assert {
        "ACC_VIEW",
        "ACC_EDIT",
        "SALES_VIEW",
        "PURCHASES_VIEW",
        "purchases.invoice.manage",
        "purchases.payments.manage",
        "inventory.approve_value",
    }.issubset(finance_permissions)
    assert {
        "ACC_VIEW",
        "ACC_EDIT",
        "inventory.approve_value",
    }.issubset(manager_permissions)
    assert "stock.adjust" not in technico_permissions
    assert "inventory.validate" not in technico_permissions
    assert "TECHNICO_COMMERCIAL" in BE_REVIEW_ROLES


def test_finance_can_manage_accounting_but_viewer_cannot_mutate(isolated_client):
    client, session_factory = isolated_client
    finance_headers = _seed_access(
        session_factory,
        "finance-test",
        "FINANCE",
        ["ACC_VIEW", "ACC_EDIT"],
    )
    viewer_headers = _seed_access(
        session_factory,
        "finance-viewer",
        "FINANCE_VIEWER",
        ["ACC_VIEW"],
    )

    created = client.post(
        "/v2/accounting/invoices",
        headers=finance_headers,
        json=_invoice_payload(),
    )
    assert created.status_code == 200, created.text

    listed = client.get("/v2/accounting/invoices", headers=finance_headers)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1

    exported = client.get("/v2/accounting/export/fec", headers=finance_headers)
    assert exported.status_code == 200, exported.text

    viewer_listed = client.get("/v2/accounting/invoices", headers=viewer_headers)
    assert viewer_listed.status_code == 200, viewer_listed.text

    viewer_create = client.post(
        "/v2/accounting/invoices",
        headers=viewer_headers,
        json=_invoice_payload(),
    )
    assert viewer_create.status_code == 403

    viewer_export = client.get("/v2/accounting/export/fec", headers=viewer_headers)
    assert viewer_export.status_code == 403


def test_finance_supplier_invoice_permissions_are_independent_from_purchase_approval(isolated_client):
    client, session_factory = isolated_client
    finance_headers = _seed_access(
        session_factory,
        "supplier-finance-test",
        "FINANCE",
        ["purchases.invoice.manage", "purchases.payments.manage"],
    )
    viewer_headers = _seed_access(
        session_factory,
        "supplier-finance-viewer",
        "FINANCE_VIEWER",
        ["ACC_VIEW"],
    )
    invoice_payload = {
        "supplier_reference": "FAC-TEST",
        "lines": [{"purchase_order_line_id": 1, "quantity": 1}],
    }

    finance_match = client.post(
        "/v2/purchases/999999/supplier-invoices",
        headers=finance_headers,
        json=invoice_payload,
    )
    assert finance_match.status_code == 404

    viewer_match = client.post(
        "/v2/purchases/999999/supplier-invoices",
        headers=viewer_headers,
        json=invoice_payload,
    )
    assert viewer_match.status_code == 403

    finance_payment = client.post(
        "/v2/purchases/supplier-invoices/999999/pay",
        headers=finance_headers,
        json={"amount": 1, "method": "TRANSFER"},
    )
    assert finance_payment.status_code == 404

    viewer_payment = client.post(
        "/v2/purchases/supplier-invoices/999999/pay",
        headers=viewer_headers,
        json={"amount": 1, "method": "TRANSFER"},
    )
    assert viewer_payment.status_code == 403
