from dataclasses import dataclass
from typing import Optional

import logging

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models


logger = logging.getLogger(__name__)


@dataclass
class StockMoveResult:
    move: models.StockMove
    previous_source_quantity: Optional[float] = None
    new_source_quantity: Optional[float] = None
    previous_dest_quantity: Optional[float] = None
    new_dest_quantity: Optional[float] = None


class InventoryService:
    @staticmethod
    def get_or_create_location(db: Session, name: str, usage: str = "internal") -> models.StockLocation:
        location = db.query(models.StockLocation).filter_by(name=name, usage=usage).first()
        if not location:
            location = models.StockLocation(name=name, usage=usage, is_active=True)
            db.add(location)
            db.flush()
        return location

    @staticmethod
    def get_or_create_quant(db: Session, variant_id: int, location_id: int, *, for_update: bool = False) -> models.StockQuant:
        def _query():
            query = db.query(models.StockQuant).filter_by(variant_id=variant_id, location_id=location_id)
            # Vrai FOR UPDATE sur PostgreSQL ; clause ignorée sans effet sur SQLite.
            return query.with_for_update() if for_update else query

        quant = _query().first()
        if quant is not None:
            return quant

        # Course read-then-create : insertion atomique arbitrée par la
        # contrainte d'unicité uq_stock_quants_variant_location
        # (INSERT ... ON CONFLICT DO NOTHING sur SQLite >= 3.24 et
        # PostgreSQL >= 9.5). Le perdant ne fait rien puis relit (et
        # verrouille) la ligne gagnante. La session n'est jamais mise en
        # échec : contrairement au flush dans un savepoint (pattern
        # document_sequences), aucune IntegrityError n'est levée, ce qui
        # évite de désactiver la transaction ORM appelante.
        table = models.StockQuant.__table__
        values = {"variant_id": variant_id, "location_id": location_id, "quantity": 0}
        if db.get_bind().dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(table).values(**values).on_conflict_do_nothing(
                index_elements=["variant_id", "location_id"]
            )
        else:
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert
            stmt = sqlite_insert(table).values(**values).on_conflict_do_nothing(
                index_elements=["variant_id", "location_id"]
            )
        db.execute(stmt)

        quant = _query().first()
        if quant is None:  # défensif : l'insertion ou la ligne concurrente existe forcément
            raise IntegrityError("INSERT ON CONFLICT DO NOTHING", values, None)
        return quant

    @staticmethod
    def sync_variant_internal_stock(db: Session, variant_id: int) -> None:
        variant = db.query(models.ProductVariant).filter_by(id=variant_id).first()
        if not variant:
            return
        internal_quants = (
            db.query(models.StockQuant)
            .join(models.StockLocation, models.StockQuant.location_id == models.StockLocation.id)
            .filter(
                models.StockQuant.variant_id == variant_id,
                models.StockLocation.usage == "internal",
                models.StockLocation.is_active == True,
            )
            .all()
        )
        variant.quantity_in_stock = sum(float(quant.quantity or 0) for quant in internal_quants)

    @staticmethod
    def locked_inventory_session_for_location(db: Session, location_id: int) -> Optional[models.InventorySession]:
        location = db.query(models.StockLocation).filter_by(id=location_id, is_active=True).first()
        if not location or location.usage != "internal":
            return None
        # La zone d'une campagne couvre sa cible ET tous ses descendants
        # (miroir de ``_zone_location_ids`` côté router). Un mouvement sur un
        # emplacement enfant d'une campagne ouverte sur l'entrepôt parent doit
        # donc être bloqué : on remonte la chaîne ``parent_id`` depuis
        # l'emplacement du mouvement et on bloque si une campagne gelée vise
        # un ancêtre (ou est globale). La garde ``visited`` neutralise tout
        # cycle parent_id corrompu.
        ancestor_ids = []
        visited = set()
        current = location
        while current is not None and current.id not in visited:
            visited.add(current.id)
            ancestor_ids.append(current.id)
            if current.parent_id is None:
                break
            current = db.query(models.StockLocation).filter_by(id=current.parent_id).first()
        return (
            db.query(models.InventorySession)
            .filter(
                models.InventorySession.zone_locked == True,
                models.InventorySession.status.in_(["draft", "counting"]),
                or_(
                    models.InventorySession.location_id == None,
                    models.InventorySession.location_id.in_(ancestor_ids),
                ),
            )
            .order_by(models.InventorySession.created_at.desc())
            .first()
        )

    @classmethod
    def assert_location_not_locked(cls, db: Session, location_id: int) -> None:
        locked_session = cls.locked_inventory_session_for_location(db, location_id)
        if locked_session:
            raise ValueError(
                f"Zone gelée par la campagne d'inventaire {locked_session.reference}. "
                "Validez ou annulez la campagne avant de créer un mouvement stock."
            )

    @staticmethod
    def _warn_if_reservation_breached(
        db: Session,
        variant: models.ProductVariant,
        source_location: Optional[models.StockLocation],
        remaining_quantity: float,
        *,
        source_screen: Optional[str],
        document_type: Optional[str],
        document_reference: Optional[str],
    ) -> None:
        """Avertit quand une sortie interne perce une réservation ferme.

        Limite assumée (documentée) : seul le PHYSIQUE est bloquant dans le
        moteur à quants — il n'existe pas de quant « réservé » séparé. Une
        sortie hors consommation de réservation (POS, vente, ajustement) peut
        donc encore prendre du stock réservé ; le re-contrôle transactionnel
        à la consommation (``assert_consumable_at_location``) refuse alors le
        débit avec une erreur métier explicite. Ce warning rend la cassure
        visible dans les logs dès la sortie fautive, sans bloquer les flux
        légitimes (ex. déstockage d'urgence).
        """
        if not source_location or source_location.usage != "internal":
            return
        if document_type in {"stock_reservation", "workshop_preparation"}:
            # Consommation/retour de réservation : le réservé de cette
            # réservation est légitimement prélevé. La préparation atelier
            # déplace ce réservé vers une zone interne dédiée.
            return
        from .stock_reservations import active_reserved_quantity

        reserved = active_reserved_quantity(db, variant.id, location_id=source_location.id)
        if reserved > remaining_quantity + 1e-9:
            logger.warning(
                "Réservation percée : sortie interne (écran=%s, document=%s/%s) de la variante #%s (%s) "
                "depuis « %s » — reste %g < réservé actif %g. Une réservation ferme échouera au débit "
                "(re-contrôle 409).",
                source_screen or "inconnu",
                document_type or "inconnu",
                document_reference or "-",
                variant.id,
                variant.reference,
                source_location.name,
                remaining_quantity,
                reserved,
            )

    @classmethod
    def move_stock(
        cls,
        db: Session,
        *,
        variant_id: int,
        quantity: float,
        source_location_id: Optional[int] = None,
        dest_location_id: Optional[int] = None,
        reference: str,
        notes: Optional[str] = None,
        author: str = "Système",
        source_screen: Optional[str] = None,
        document_type: Optional[str] = None,
        document_reference: Optional[str] = None,
        business_reason: Optional[str] = None,
        state: str = "done",
        allow_negative_source: bool = False,
        enforce_zone_lock: bool = True,
    ) -> StockMoveResult:
        qty = abs(float(quantity or 0))
        if qty <= 0:
            raise ValueError("La quantité du mouvement stock doit être positive.")
        if not source_location_id and not dest_location_id:
            raise ValueError("Un mouvement stock doit avoir une source ou une destination.")

        variant = db.query(models.ProductVariant).filter_by(id=variant_id).first()
        if not variant:
            raise ValueError("Variante introuvable.")

        source_location = db.query(models.StockLocation).filter_by(id=source_location_id).first() if source_location_id else None
        dest_location = db.query(models.StockLocation).filter_by(id=dest_location_id).first() if dest_location_id else None
        if source_location_id and not source_location:
            raise ValueError("Emplacement source introuvable.")
        if dest_location_id and not dest_location:
            raise ValueError("Emplacement destination introuvable.")

        if enforce_zone_lock:
            if source_location_id:
                cls.assert_location_not_locked(db, source_location_id)
            if dest_location_id:
                cls.assert_location_not_locked(db, dest_location_id)

        previous_source_quantity = None
        new_source_quantity = None
        previous_dest_quantity = None
        new_dest_quantity = None

        # Verrouillage pessimiste des quants touchés (FOR UPDATE sur
        # PostgreSQL, no-op sur SQLite) dans un ordre déterministe (ids
        # croissants) pour éviter les interblocages entre transactions.
        quant_location_ids = sorted({lid for lid in (source_location_id, dest_location_id) if lid})
        quants = {
            lid: cls.get_or_create_quant(db, variant_id, lid, for_update=True)
            for lid in quant_location_ids
        }

        if source_location_id:
            source_quant = quants[source_location_id]
            previous_source_quantity = float(source_quant.quantity or 0)
            source_can_go_negative = allow_negative_source or (source_location and source_location.usage in {"supplier", "inventory"})
            if previous_source_quantity < qty and not source_can_go_negative:
                raise ValueError(f"Stock source insuffisant: {previous_source_quantity:g} < {qty:g}.")
            source_quant.quantity = previous_source_quantity - qty
            new_source_quantity = float(source_quant.quantity or 0)
            cls._warn_if_reservation_breached(
                db,
                variant,
                source_location,
                new_source_quantity,
                source_screen=source_screen,
                document_type=document_type,
                document_reference=document_reference,
            )

        if dest_location_id:
            dest_quant = quants[dest_location_id]
            previous_dest_quantity = float(dest_quant.quantity or 0)
            dest_quant.quantity = previous_dest_quantity + qty
            new_dest_quantity = float(dest_quant.quantity or 0)

        move = models.StockMove(
            reference=reference,
            variant_id=variant_id,
            location_id=source_location_id,
            location_dest_id=dest_location_id,
            quantity=qty,
            state=state,
            notes=notes,
            author=author,
            source_screen=source_screen,
            document_type=document_type,
            document_reference=document_reference,
            business_reason=business_reason,
        )
        db.add(move)
        db.flush()
        cls.sync_variant_internal_stock(db, variant_id)
        return StockMoveResult(
            move=move,
            previous_source_quantity=previous_source_quantity,
            new_source_quantity=new_source_quantity,
            previous_dest_quantity=previous_dest_quantity,
            new_dest_quantity=new_dest_quantity,
        )


class StockService:
    @staticmethod
    def deduct_stock_for_order(db: Session, order_id: int, station_code: str, author: str = "Système"):
        if "DEBIT" not in station_code.upper():
            return {"created_moves": 0, "consumed_lines": 0, "reservations": 0}

        order = db.query(models.Order).filter(models.Order.id == order_id).first()
        if not order:
            return {"created_moves": 0, "consumed_lines": 0, "reservations": 0}

        from .stock_reservations import consume_reservations_for_order

        return consume_reservations_for_order(db, order.reference, station_code, author=author)
