from datetime import date, datetime
from decimal import Decimal
import os
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import DateTime, Numeric, text
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db


router = APIRouter(prefix="/v2/stock-migration", tags=["stock-migration"])

TOKEN_FILE = os.environ.get("STOCK_MIGRATION_TOKEN_FILE", "/tmp/mmg_stock_migration_token")


class StockMigrationImport(BaseModel):
    confirm: str
    replace: bool = False
    tables: dict[str, list[dict[str, Any]]]


TABLES: dict[str, type] = {
    "suppliers": models.Supplier,
    "products": models.Product,
    "product_variants": models.ProductVariant,
    "stock_locations": models.StockLocation,
    "stock_quants": models.StockQuant,
    "stock_moves": models.StockMove,
    "product_audit_logs": models.ProductAuditLog,
    "inventory_sessions": models.InventorySession,
    "inventory_count_lines": models.InventoryCountLine,
}

EXPORT_ORDER = list(TABLES)
IMPORT_ORDER = [
    "suppliers",
    "products",
    "product_variants",
    "stock_locations",
    "stock_quants",
    "stock_moves",
    "product_audit_logs",
    "inventory_sessions",
    "inventory_count_lines",
]
DELETE_ORDER = list(reversed(IMPORT_ORDER))


def _active_token() -> str | None:
    token = os.environ.get("STOCK_MIGRATION_TOKEN")
    if token:
        return token.strip()
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except FileNotFoundError:
        return None


def _require_token(x_stock_migration_token: str | None = Header(default=None)) -> None:
    expected = _active_token()
    if not expected:
        raise HTTPException(status_code=404, detail="Migration stock désactivée.")
    if not x_stock_migration_token or not secrets.compare_digest(x_stock_migration_token, expected):
        raise HTTPException(status_code=403, detail="Token migration invalide.")


def _serialize(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _coerce_value(column, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(column.type, DateTime):
        return datetime.fromisoformat(value)
    if isinstance(column.type, Numeric):
        return Decimal(str(value))
    return value


def _coerce_row(model: type, row: dict[str, Any]) -> dict[str, Any]:
    columns = {column.name: column for column in model.__table__.columns}
    return {
        name: _coerce_value(columns[name], value)
        for name, value in row.items()
        if name in columns
    }


def _table_counts(db: Session) -> dict[str, int]:
    return {name: db.query(model).count() for name, model in TABLES.items()}


def _reset_sequence(db: Session, table_name: str) -> None:
    dialect = db.bind.dialect.name if db.bind is not None else ""
    if dialect == "postgresql":
        db.execute(
            text(
                f"""
                SELECT setval(
                    pg_get_serial_sequence('{table_name}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {table_name}), 1),
                    true
                )
                """
            )
        )
    elif dialect == "sqlite":
        db.execute(
            text(
                "UPDATE sqlite_sequence SET seq = "
                f"COALESCE((SELECT MAX(id) FROM {table_name}), 0) "
                "WHERE name = :table_name"
            ),
            {"table_name": table_name},
        )


def _export_rows(db: Session, model: type) -> list[dict[str, Any]]:
    columns = [column.name for column in model.__table__.columns]
    return [
        {column: _serialize(getattr(record, column)) for column in columns}
        for record in db.query(model).order_by(model.id.asc()).all()
    ]


@router.get("/export", dependencies=[Depends(_require_token)])
def export_stock_data(db: Session = Depends(get_db)):
    return {
        "exported_at": datetime.utcnow().isoformat(),
        "tables": {
            table_name: _export_rows(db, model)
            for table_name, model in TABLES.items()
        },
        "counts": _table_counts(db),
    }


@router.get("/status", dependencies=[Depends(_require_token)])
def stock_migration_status(db: Session = Depends(get_db)):
    return {"counts": _table_counts(db)}


@router.post("/import", dependencies=[Depends(_require_token)])
def import_stock_data(payload: StockMigrationImport, db: Session = Depends(get_db)):
    if payload.confirm != "IMPORT_PREPROD_STOCK_DATA":
        raise HTTPException(status_code=400, detail="Confirmation migration invalide.")

    existing_counts = _table_counts(db)
    non_empty = {name: count for name, count in existing_counts.items() if count}
    if non_empty and not payload.replace:
        raise HTTPException(
            status_code=409,
            detail={"message": "Tables stock non vides.", "counts": non_empty},
        )

    missing = [name for name in IMPORT_ORDER if name not in payload.tables]
    if missing:
        raise HTTPException(status_code=400, detail=f"Tables manquantes: {', '.join(missing)}")

    try:
        if payload.replace:
            for table_name in DELETE_ORDER:
                db.query(TABLES[table_name]).delete(synchronize_session=False)
            db.flush()

        for table_name in IMPORT_ORDER:
            model = TABLES[table_name]
            rows = payload.tables.get(table_name) or []
            if not rows:
                continue
            if table_name == "stock_locations":
                location_rows = []
                parent_updates = []
                for row in rows:
                    coerced = _coerce_row(model, row)
                    parent_updates.append((coerced.get("id"), coerced.get("parent_id")))
                    coerced["parent_id"] = None
                    location_rows.append(coerced)
                db.execute(model.__table__.insert(), location_rows)
                for location_id, parent_id in parent_updates:
                    if parent_id:
                        db.query(model).filter(model.id == location_id).update({"parent_id": parent_id})
                continue
            db.execute(model.__table__.insert(), [_coerce_row(model, row) for row in rows])

        for table_name in IMPORT_ORDER:
            _reset_sequence(db, table_name)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "status": "imported",
        "before": existing_counts,
        "after": _table_counts(db),
    }
