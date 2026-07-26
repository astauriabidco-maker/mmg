"""Synchronise le pipeline CRM avec les preuves du workflow métier."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from ..core.time import utcnow


STAGE_PROBABILITIES = {
    models.CRMOpportunityStage.NEW.value: 10,
    models.CRMOpportunityStage.QUALIFIED.value: 30,
    models.CRMOpportunityStage.MEASURE_TO_SCHEDULE.value: 40,
    models.CRMOpportunityStage.MEASURE_IN_PROGRESS.value: 50,
    models.CRMOpportunityStage.PROPOSAL_TO_PREPARE.value: 60,
    models.CRMOpportunityStage.PROPOSAL_TO_VALIDATE.value: 65,
    models.CRMOpportunityStage.PROPOSAL_SENT.value: 70,
    models.CRMOpportunityStage.NEGOTIATION.value: 80,
    models.CRMOpportunityStage.WON.value: 100,
    models.CRMOpportunityStage.LOST.value: 0,
}

STAGE_RANK = {
    models.CRMOpportunityStage.NEW.value: 0,
    models.CRMOpportunityStage.QUALIFIED.value: 1,
    models.CRMOpportunityStage.MEASURE_TO_SCHEDULE.value: 2,
    models.CRMOpportunityStage.MEASURE_IN_PROGRESS.value: 3,
    models.CRMOpportunityStage.PROPOSAL_TO_PREPARE.value: 4,
    models.CRMOpportunityStage.PROPOSAL_TO_VALIDATE.value: 5,
    models.CRMOpportunityStage.PROPOSAL_SENT.value: 6,
    models.CRMOpportunityStage.NEGOTIATION.value: 7,
    models.CRMOpportunityStage.WON.value: 8,
}


def set_opportunity_stage(
    db: Session,
    opportunity: models.CRMOpportunity,
    target_stage: str,
    actor: str,
    *,
    next_milestone: Optional[str] = None,
    allow_regression: bool = False,
) -> bool:
    """Change l'étape avec historique, sans commit de la transaction appelante."""

    if opportunity.stage in {
        models.CRMOpportunityStage.WON.value,
        models.CRMOpportunityStage.LOST.value,
    } and not allow_regression:
        return False
    if target_stage == opportunity.stage:
        if next_milestone is not None:
            opportunity.next_milestone = next_milestone
        return False
    if (
        not allow_regression
        and STAGE_RANK.get(target_stage, -1) < STAGE_RANK.get(opportunity.stage, -1)
    ):
        return False

    changed_at = utcnow()
    previous_stage = opportunity.stage
    opportunity.stage = target_stage
    opportunity.stage_entered_at = changed_at
    opportunity.probability = STAGE_PROBABILITIES.get(
        target_stage,
        opportunity.probability,
    )
    if next_milestone is not None:
        opportunity.next_milestone = next_milestone
    if target_stage == models.CRMOpportunityStage.WON.value:
        opportunity.won_at = opportunity.won_at or changed_at
        opportunity.lost_at = None
        opportunity.loss_reason = None
        opportunity.next_milestone = None

    db.add(
        models.CRMOpportunityStageHistory(
            opportunity_id=opportunity.id,
            from_stage=previous_stage,
            to_stage=target_stage,
            changed_by=actor,
            changed_at=changed_at,
        )
    )
    (
        db.query(models.CRMReminderPlan)
        .filter(
            models.CRMReminderPlan.opportunity_id == opportunity.id,
            models.CRMReminderPlan.status == "PENDING",
        )
        .update(
            {
                models.CRMReminderPlan.status: "CANCELLED",
                models.CRMReminderPlan.cancelled_reason: "Étape métier synchronisée",
            },
            synchronize_session=False,
        )
    )
    return True


def sync_opportunity_from_mission(
    db: Session,
    mission: models.MeasureMission,
    actor: str,
) -> bool:
    opportunity = mission.opportunity
    if not opportunity:
        return False
    if mission.sale_order:
        return sync_opportunity_from_sale(db, mission.sale_order, actor)

    if mission.status in {
        models.MeasureMissionStatus.DRAFT.value,
        models.MeasureMissionStatus.TO_SCHEDULE.value,
        models.MeasureMissionStatus.SCHEDULED.value,
    }:
        if mission.source_type == "SITE_VISIT":
            target = models.CRMOpportunityStage.MEASURE_TO_SCHEDULE.value
            milestone = "Planifier et réaliser le métré"
        else:
            target = models.CRMOpportunityStage.MEASURE_IN_PROGRESS.value
            milestone = "Compléter les cotes et documents du dossier"
    elif mission.status in {
        models.MeasureMissionStatus.IN_CAPTURE.value,
        models.MeasureMissionStatus.ON_SITE.value,
        models.MeasureMissionStatus.TO_REVIEW.value,
        models.MeasureMissionStatus.CORRECTION_REQUIRED.value,
    }:
        target = models.CRMOpportunityStage.MEASURE_IN_PROGRESS.value
        milestone = (
            "Corriger puis soumettre les ouvrages au contrôle BE"
            if mission.status == models.MeasureMissionStatus.CORRECTION_REQUIRED.value
            else "Finaliser le métré et le contrôle BE"
        )
    elif mission.status == models.MeasureMissionStatus.VALIDATED.value:
        target = models.CRMOpportunityStage.PROPOSAL_TO_PREPARE.value
        quoting_status = (
            mission.technical_dossier.quoting_status
            if mission.technical_dossier
            else None
        )
        if quoting_status == "TO_REVIEW":
            milestone = "Faire valider le chiffrage PROGES/ORGADATA par le BE"
        elif quoting_status == "CORRECTION_REQUIRED":
            milestone = "Corriger le chiffrage PROGES/ORGADATA"
        elif quoting_status == "VALIDATED":
            milestone = "Générer la proposition depuis le chiffrage validé"
        else:
            milestone = "Importer le chiffrage PROGES/ORGADATA"
    else:
        return False

    return set_opportunity_stage(
        db,
        opportunity,
        target,
        actor,
        next_milestone=milestone,
    )


def sync_opportunity_from_sale(
    db: Session,
    sale: models.SaleOrder,
    actor: str,
) -> bool:
    opportunity = (
        db.query(models.CRMOpportunity)
        .filter(models.CRMOpportunity.sale_order_id == sale.id)
        .first()
    )
    if not opportunity:
        return False

    if sale.signed_at or sale.status in {
        "VALIDATED",
        "ACCEPTED",
        "IN_DESIGN",
        "READY_FOR_PROD",
        "IN_PRODUCTION",
        "DELIVERED",
    }:
        target = models.CRMOpportunityStage.WON.value
        milestone = None
    elif sale.status == "SENT":
        target = models.CRMOpportunityStage.PROPOSAL_SENT.value
        milestone = "Relancer le client et obtenir sa décision"
    elif sale.status == "DRAFT":
        priced = bool(sale.lines) and all(
            float(line.unit_price or 0) > 0 for line in sale.lines
        )
        target = (
            models.CRMOpportunityStage.PROPOSAL_TO_VALIDATE.value
            if priced
            else models.CRMOpportunityStage.PROPOSAL_TO_PREPARE.value
        )
        milestone = (
            "Contrôler puis envoyer la proposition"
            if priced
            else "Compléter les prix du chiffrage"
        )
    else:
        return False

    return set_opportunity_stage(
        db,
        opportunity,
        target,
        actor,
        next_milestone=milestone,
    )
