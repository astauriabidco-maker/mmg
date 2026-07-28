"""Client CRM normalization, duplicate detection and controlled merges."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Iterable

from sqlalchemy.orm import Session

from .. import models
from ..core.time import utcnow


def normalize_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def normalize_phone(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits[-9:] if len(digits) > 9 else digits


def normalize_tags(values: Iterable[str] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        label = str(value or "").strip()
        key = normalize_text(label)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(label[:80])
    return result[:30]


def duplicate_score(
    first: models.Client,
    second: models.Client,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    first_email = normalize_email(first.email)
    second_email = normalize_email(second.email)
    if first_email and first_email == second_email:
        score += 100
        reasons.append("Même email")

    first_phone = normalize_phone(first.phone)
    second_phone = normalize_phone(second.phone)
    if first_phone and first_phone == second_phone:
        score += 90
        reasons.append("Même téléphone")

    first_tax = normalize_text(first.tax_id)
    second_tax = normalize_text(second.tax_id)
    if first_tax and first_tax == second_tax:
        score += 100
        reasons.append("Même identifiant fiscal")

    first_name = normalize_text(first.name)
    second_name = normalize_text(second.name)
    if first_name and first_name == second_name:
        score += 60
        reasons.append("Même nom")
        first_address = normalize_text(first.address)
        second_address = normalize_text(second.address)
        if first_address and first_address == second_address:
            score += 25
            reasons.append("Même adresse")

    return min(score, 100), reasons


def duplicate_candidates(
    clients: Iterable[models.Client],
    reference: models.Client,
    *,
    minimum_score: int = 60,
) -> list[tuple[models.Client, int, list[str]]]:
    matches = []
    for candidate in clients:
        if candidate.id == reference.id:
            continue
        score, reasons = duplicate_score(reference, candidate)
        if score >= minimum_score:
            matches.append((candidate, score, reasons))
    return sorted(matches, key=lambda item: (-item[1], item[0].name.lower()))


def duplicate_groups(
    clients: list[models.Client],
    *,
    minimum_score: int = 80,
) -> list[tuple[list[models.Client], int, list[str]]]:
    parents = {client.id: client.id for client in clients}
    pair_details: dict[tuple[int, int], tuple[int, list[str]]] = {}

    def find(client_id: int) -> int:
        while parents[client_id] != client_id:
            parents[client_id] = parents[parents[client_id]]
            client_id = parents[client_id]
        return client_id

    def union(first_id: int, second_id: int) -> None:
        first_root = find(first_id)
        second_root = find(second_id)
        if first_root != second_root:
            parents[second_root] = first_root

    for index, first in enumerate(clients):
        for second in clients[index + 1 :]:
            score, reasons = duplicate_score(first, second)
            if score < minimum_score:
                continue
            pair_details[(first.id, second.id)] = (score, reasons)
            union(first.id, second.id)

    grouped: dict[int, list[models.Client]] = defaultdict(list)
    for client in clients:
        grouped[find(client.id)].append(client)

    result = []
    for group in grouped.values():
        if len(group) < 2:
            continue
        group_ids = {client.id for client in group}
        group_scores = []
        reasons = set()
        for (first_id, second_id), (score, pair_reasons) in pair_details.items():
            if first_id in group_ids and second_id in group_ids:
                group_scores.append(score)
                reasons.update(pair_reasons)
        result.append(
            (
                sorted(group, key=lambda client: client.created_at or utcnow()),
                max(group_scores or [0]),
                sorted(reasons),
            )
        )
    return sorted(result, key=lambda item: (-item[1], item[0][0].name.lower()))


def merge_clients(
    db: Session,
    target: models.Client,
    sources: list[models.Client],
    *,
    actor: str,
) -> dict[str, int]:
    """Move all CRM records to ``target`` and remove the source clients."""

    moved: dict[str, int] = {}
    source_ids = [source.id for source in sources]
    if not source_ids:
        return moved

    scalar_fields = (
        "contact_name",
        "email",
        "phone",
        "address",
        "country",
        "tax_id",
        "customer_type",
        "segment",
    )
    for source in sources:
        for field in scalar_fields:
            if not getattr(target, field, None) and getattr(source, field, None):
                setattr(target, field, getattr(source, field))
        target.tags = normalize_tags([*(target.tags or []), *(source.tags or [])])

    tables = (
        ("calendar_tasks", models.CalendarTask),
        ("mmg_dossiers", models.MMG),
        ("sites", models.ClientSiteAddress),
        ("opportunities", models.CRMOpportunity),
        ("activities", models.CRMActivity),
        ("reminder_plans", models.CRMReminderPlan),
        ("reminder_deliveries", models.CRMReminderDelivery),
        ("measure_missions", models.MeasureMission),
        ("contacts", models.ClientContact),
    )
    for label, model in tables:
        count = (
            db.query(model)
            .filter(model.client_id.in_(source_ids))
            .update(
                {model.client_id: target.id},
                synchronize_session=False,
            )
        )
        moved[label] = count

    db.flush()
    contacts = (
        db.query(models.ClientContact)
        .filter(models.ClientContact.client_id == target.id)
        .order_by(
            models.ClientContact.is_primary.desc(),
            models.ClientContact.created_at.asc(),
            models.ClientContact.id.asc(),
        )
        .all()
    )
    for index, contact in enumerate(contacts):
        contact.is_primary = index == 0
    if contacts:
        primary = contacts[0]
        target.contact_name = primary.name
        target.email = primary.email or target.email
        target.phone = primary.phone or target.phone

    for source in sources:
        db.delete(source)

    db.add(
        models.CRMActivity(
            client_id=target.id,
            activity_type=models.CRMActivityType.NOTE.value,
            subject="Fiches clients fusionnées",
            note=(
                f"Fusion des clients {', '.join(str(source_id) for source_id in source_ids)} "
                f"dans la fiche #{target.id} par {actor}."
            ),
            status=models.CRMActivityStatus.COMPLETED.value,
            author=actor,
            completed_at=utcnow(),
        )
    )
    return moved
