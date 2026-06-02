#!/usr/bin/env python3
"""Run a lightweight functional audit against the local MMG app.

The script intentionally uses only the Python standard library so it can run
inside the project virtualenv without extra browser or test dependencies.
It creates records prefixed with AUDIT so the exercised flows are traceable.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Finding:
    severity: str
    area: str
    message: str
    detail: str = ""


class AuditClient:
    def __init__(self, api_base: str, frontend_base: str, username: str, password: str):
        self.api_base = api_base.rstrip("/")
        self.frontend_base = frontend_base.rstrip("/")
        self.username = username
        self.password = password
        self.token: str | None = None

    def request(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        auth: bool = True,
        timeout: int = 8,
    ) -> tuple[int, Any]:
        url = self.api_base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)

        body = None
        headers: dict[str, str] = {}
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, self._decode(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, self._decode(exc.read())

    def raw_get(self, url: str, timeout: int = 8) -> tuple[int, str]:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")

    def login(self) -> tuple[int, Any]:
        body = urllib.parse.urlencode(
            {"username": self.username, "password": self.password}
        ).encode("utf-8")
        request = urllib.request.Request(
            self.api_base + "/token",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = self._decode(response.read())
                self.token = payload.get("access_token") if isinstance(payload, dict) else None
                return response.status, payload
        except urllib.error.HTTPError as exc:
            return exc.code, self._decode(exc.read())

    @staticmethod
    def _decode(raw: bytes) -> Any:
        text = raw.decode("utf-8", "replace")
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text


class FunctionalAudit:
    def __init__(self, client: AuditClient, project_root: Path, mutate: bool):
        self.client = client
        self.project_root = project_root
        self.mutate = mutate
        self.findings: list[Finding] = []
        self.run_id = f"AUDIT-{time.time_ns()}"

    def add(self, severity: str, area: str, message: str, detail: str = "") -> None:
        self.findings.append(Finding(severity, area, message, detail))

    def expect_status(
        self,
        area: str,
        label: str,
        status: int,
        expected: int | set[int],
        detail: str = "",
    ) -> bool:
        expected_set = expected if isinstance(expected, set) else {expected}
        if status in expected_set:
            self.add("OK", area, label, detail or f"HTTP {status}")
            return True
        self.add("FAIL", area, label, detail or f"Attendu {sorted(expected_set)}, reçu {status}")
        return False

    def run(self) -> int:
        self.check_frontend()
        self.check_login()
        if self.client.token:
            self.check_auth_matrix()
            self.check_reference_data()
            if self.mutate:
                self.check_sales_signature_invoice()
                self.check_workshop_production()
                self.check_purchase_stock()
            else:
                self.add(
                    "INFO",
                    "Mode",
                    "Scénarios mutatifs ignorés",
                    "Relancer sans --no-mutate pour tester devis, atelier et achats.",
                )
        self.check_source_inconsistencies()
        self.print_report()
        return 1 if any(f.severity == "FAIL" for f in self.findings) else 0

    def check_frontend(self) -> None:
        status, body = self.client.raw_get(self.client.frontend_base + "/login")
        self.expect_status("Frontend", "Page login accessible", status, 200)
        if status == 200 and "Atelier Connecté" not in body and "<script" not in body:
            self.add("WARN", "Frontend", "HTML login inattendu", body[:180])

    def check_login(self) -> None:
        status, payload = self.client.login()
        if self.expect_status("Auth", "Login admin", status, 200):
            role = payload.get("role") if isinstance(payload, dict) else None
            if role != "ADMIN":
                self.add("WARN", "Auth", "Le compte audit n'a pas le rôle ADMIN", f"role={role!r}")

    def check_auth_matrix(self) -> None:
        protected_paths = [
            "/v2/analytics/kpi",
            "/v2/ingest/orders/tracking",
            "/v2/config/stations",
            "/v2/stock/products",
            "/v2/sales/",
            "/v2/accounting/invoices",
            "/v2/logistics/notes/ready",
            "/v2/pos/items",
        ]
        for path in protected_paths:
            status, _ = self.client.request("GET", path, auth=False)
            self.expect_status("Auth", f"{path} bloque l'accès sans token", status, 401)
            status, _ = self.client.request("GET", path, auth=True)
            self.expect_status("Auth", f"{path} répond avec token", status, {200, 404})

    def check_reference_data(self) -> None:
        status, stations = self.client.request("GET", "/v2/config/stations")
        if self.expect_status("Référentiels", "Stations configurées accessibles", status, 200):
            count = len(stations) if isinstance(stations, list) else 0
            if count == 0:
                self.add("FAIL", "Référentiels", "Aucune station configurée")
            else:
                self.add("OK", "Référentiels", f"{count} stations disponibles")

    def check_sales_signature_invoice(self) -> None:
        area = "Flux devis"
        payload = {
            "client_name": f"{self.run_id} Client",
            "client_contact": "Audit",
            "client_email": "audit@example.test",
            "client_address": "1 rue Audit, 75000 Paris",
            "validity_days": 15,
            "tax_rate": 20.0,
            "currency": "EUR",
            "notes": self.run_id,
            "lines": [
                {
                    "variant_id": None,
                    "description": f"{self.run_id} Menuiserie",
                    "quantity": 1,
                    "unit_price": 1000.0,
                    "discount_pct": 0,
                    "visual_config": None,
                }
            ],
        }
        status, sale = self.client.request("POST", "/v2/sales/", data=payload)
        if not self.expect_status(area, "Création devis", status, 200):
            return

        sale_id = sale["id"]
        status, sent = self.client.request(
            "PUT", f"/v2/sales/{sale_id}/status", params={"status": "SENT"}
        )
        if not self.expect_status(area, "Passage devis en SENT", status, 200):
            return

        status, refreshed = self.client.request("GET", f"/v2/sales/{sale_id}")
        token = refreshed.get("signature_token") if isinstance(refreshed, dict) else None
        if not token:
            self.add("FAIL", area, "Aucun signature_token après statut SENT")
            return

        portal_link = sent.get("portal_link") if isinstance(sent, dict) else ""
        if not portal_link.endswith(f"/portal/sign/{token}"):
            self.add("WARN", area, "Lien portail incohérent avec le token", str(portal_link))

        status, public_quote = self.client.request("GET", f"/v2/sales/portal/{token}", auth=False)
        self.expect_status(area, "Portail devis public accessible", status, 200)

        status, _ = self.client.request("POST", f"/v2/sales/portal/{token}/sign", auth=False)
        if not self.expect_status(area, "Signature publique du devis", status, 200):
            return

        status, invoices = self.client.request("GET", "/v2/accounting/invoices")
        if self.expect_status(area, "Factures accessibles après signature", status, 200):
            matching = [
                invoice
                for invoice in invoices
                if invoice.get("client_name") == payload["client_name"]
            ]
            if not matching:
                self.add("FAIL", area, "Aucune facture générée pour le devis signé")
                return
            invoice = matching[0]
            if invoice.get("client_address") != payload["client_address"]:
                self.add(
                    "FAIL",
                    area,
                    "Adresse facture incohérente",
                    f"attendu={payload['client_address']!r}, reçu={invoice.get('client_address')!r}",
                )
            else:
                self.add("OK", area, "Facture générée avec adresse client correcte")

    def check_workshop_production(self) -> None:
        area = "Flux atelier"
        order_ref = f"{self.run_id}-ORDER"
        station = "PVC_DEBIT"
        status, _ = self.client.request(
            "POST",
            "/v2/ingest/order",
            data={
                "reference": order_ref,
                "width": 1200,
                "height": 900,
                "material": "PVC",
                "client_name": f"{self.run_id} Atelier",
                "color": "Blanc",
                "quantity": 1,
                "system_type": "Coulissant",
            },
        )
        if not self.expect_status(area, "Ingestion commande", status, 200):
            return

        status, _ = self.client.request(
            "POST", "/production/start", data={"order_reference": order_ref, "station": station}
        )
        if not self.expect_status(area, "Démarrage production", status, 200):
            return

        status, tracking = self.client.request("GET", "/v2/ingest/orders/tracking")
        tracked = self._find_by_reference(tracking, order_ref)
        if not tracked or tracked.get("status") != "IN_PROGRESS":
            self.add("FAIL", area, "Suivi commande non synchronisé après start", str(tracked))
        else:
            self.add("OK", area, "Suivi commande synchronisé en IN_PROGRESS")

        status, _ = self.client.request(
            "POST", "/production/stop", data={"order_reference": order_ref, "station": station}
        )
        if not self.expect_status(area, "Arrêt production", status, 200):
            return

        status, tracking = self.client.request("GET", "/v2/ingest/orders/tracking")
        tracked = self._find_by_reference(tracking, order_ref)
        if not tracked or tracked.get("progress") != 100:
            self.add("FAIL", area, "Progression commande non finalisée après stop", str(tracked))
        else:
            self.add("OK", area, "Suivi commande finalisé à 100%")

    def check_purchase_stock(self) -> None:
        area = "Flux achats/stock"
        reference = f"{self.run_id}-PRODUCT"
        variant_reference = f"{reference}-V1"
        status, product = self.client.request(
            "POST",
            "/v2/stock/products",
            data={
                "reference_base": reference,
                "name": f"{self.run_id} Profil",
                "material_type": "PVC",
                "unit": "ml",
                "supplier": "Fournisseur audit",
                "variants": [
                    {
                        "reference": variant_reference,
                        "color": "Blanc",
                        "cost_price": 12.5,
                        "quantity_in_stock": 0,
                        "min_threshold": 5,
                    }
                ],
            },
        )
        if not self.expect_status(area, "Création produit et variante", status, 200):
            return
        variant = product["variants"][0]
        variant_id = variant["id"]

        status, location = self.client.request(
            "POST",
            "/v2/stock/locations",
            data={"name": f"WH/{self.run_id}", "usage": "internal"},
        )
        if not self.expect_status(area, "Création emplacement réception", status, 200):
            return

        status, purchase = self.client.request(
            "POST",
            "/v2/purchases/",
            data={
                "supplier": "Fournisseur audit",
                "notes": self.run_id,
                "lines": [{"variant_id": variant_id, "quantity": 7, "unit_price": 12.5}],
            },
        )
        if not self.expect_status(area, "Création commande fournisseur", status, 200):
            return

        status, _ = self.client.request(
            "POST",
            f"/v2/purchases/{purchase['id']}/receive",
            data={"target_location_id": location["id"]},
        )
        if not self.expect_status(area, "Réception commande fournisseur", status, 200):
            return

        status, quants = self.client.request("GET", "/v2/stock/quants")
        matching_quant = [
            quant
            for quant in quants
            if quant.get("variant_id") == variant_id and quant.get("location_id") == location["id"]
        ] if isinstance(quants, list) else []
        if matching_quant and matching_quant[0].get("quantity") == 7.0:
            self.add("OK", area, "Quant de stock créé à la réception")
        else:
            self.add("FAIL", area, "Quant de stock absent ou quantité incohérente", str(matching_quant))

        status, products = self.client.request("GET", "/v2/stock/products")
        received_variant = None
        if isinstance(products, list):
            for item in products:
                for candidate in item.get("variants", []):
                    if candidate.get("id") == variant_id:
                        received_variant = candidate
                        break
        if received_variant and received_variant.get("quantity_in_stock", 0) != 7.0:
            self.add(
                "WARN",
                area,
                "Incohérence stock: ProductVariant.quantity_in_stock ne reflète pas la réception",
                f"attendu=7.0, reçu={received_variant.get('quantity_in_stock')!r}",
            )
        elif received_variant:
            self.add("OK", area, "Stock résumé variante cohérent après réception")
        else:
            self.add("WARN", area, "Variante reçue introuvable dans /v2/stock/products")

    def check_source_inconsistencies(self) -> None:
        checks = [
            ("Dashboard mock 142", "frontend_v2/src/pages/ManagerDashboard.jsx", "142"),
            ("Fausse alerte lame HS", "frontend_v2/src/pages/ManagerDashboard.jsx", "Lame H.S"),
            ("Lien portail ancien port Vite", "backend/routers/v2_sales.py", "localhost:5173/portal"),
            ("Auteur Admin hardcodé ventes", "backend/routers/v2_sales.py", 'author="Admin"'),
            ("Auteur Admin hardcodé POS", "backend/routers/v2_pos.py", 'opened_by_user="Admin"'),
        ]
        for label, relative_path, needle in checks:
            path = self.project_root / relative_path
            content = path.read_text("utf-8") if path.exists() else ""
            if needle in content:
                self.add("WARN", "Code source", label, f"{relative_path} contient {needle!r}")
            else:
                self.add("OK", "Code source", label)

    def print_report(self) -> None:
        grouped: dict[str, list[Finding]] = {}
        for finding in self.findings:
            grouped.setdefault(finding.severity, []).append(finding)

        print(f"\n# Rapport audit fonctionnel {self.run_id}\n")
        for severity in ["FAIL", "WARN", "OK", "INFO"]:
            items = grouped.get(severity, [])
            if not items:
                continue
            print(f"## {severity} ({len(items)})")
            for item in items:
                suffix = f" — {item.detail}" if item.detail else ""
                print(f"- [{item.area}] {item.message}{suffix}")
            print()

    @staticmethod
    def _find_by_reference(items: Any, reference: str) -> dict[str, Any] | None:
        if not isinstance(items, list):
            return None
        for item in items:
            if item.get("reference") == reference:
                return item
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run MMG local functional audit.")
    parser.add_argument("--api", default="http://127.0.0.1:7000")
    parser.add_argument("--frontend", default="http://127.0.0.1:5000")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="1234")
    parser.add_argument(
        "--no-mutate",
        action="store_true",
        help="Skip E2E scenarios that create AUDIT records in the local database.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    client = AuditClient(args.api, args.frontend, args.username, args.password)
    return FunctionalAudit(client, project_root, mutate=not args.no_mutate).run()


if __name__ == "__main__":
    sys.exit(main())
