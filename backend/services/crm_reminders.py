import re
from datetime import datetime, timedelta
from html import escape

from sqlalchemy.exc import IntegrityError

from .. import models
from ..core.time import utcnow


DEFAULT_TEMPLATES = (
    {
        "code": "PROPOSAL_FOLLOW_UP",
        "name": "Relance proposition",
        "description": "Relancer une proposition envoyée ou une négociation sans réponse.",
        "subject_template": "Votre proposition {{opportunity_reference}} - MMG Menuiseries",
        "body_template": (
            "Bonjour {{contact_name}},\n\n"
            "Je reviens vers vous au sujet de notre proposition {{opportunity_reference}} "
            "concernant « {{opportunity_title}} ».\n\n"
            "Avez-vous pu en prendre connaissance ? Je reste disponible pour répondre à vos "
            "questions ou ajuster les points qui le nécessitent.\n\n"
            "Bien cordialement,\n{{sender_name}}\nMMG Menuiseries"
        ),
    },
    {
        "code": "MEASURE_SCHEDULING",
        "name": "Planification du métré",
        "description": "Proposer ou confirmer l'organisation d'une prise de côte.",
        "subject_template": "Organisation de votre prise de côte - {{client_name}}",
        "body_template": (
            "Bonjour {{contact_name}},\n\n"
            "Nous souhaitons organiser la prise de côte liée à votre projet "
            "« {{opportunity_title}} ».\n\n"
            "Pouvez-vous nous indiquer vos disponibilités afin que nous convenions d'un créneau ?\n\n"
            "Bien cordialement,\n{{sender_name}}\nMMG Menuiseries"
        ),
    },
    {
        "code": "GENERAL_FOLLOW_UP",
        "name": "Reprise de contact",
        "description": "Relance commerciale générique avec contexte du dossier.",
        "subject_template": "Suivi de votre projet {{opportunity_reference}}",
        "body_template": (
            "Bonjour {{contact_name}},\n\n"
            "Je vous contacte au sujet de votre projet « {{opportunity_title}} » "
            "référencé {{opportunity_reference}}.\n\n"
            "La prochaine étape prévue est : {{next_milestone}}. "
            "Je reste à votre disposition pour avancer avec vous.\n\n"
            "Bien cordialement,\n{{sender_name}}\nMMG Menuiseries"
        ),
    },
)

DEFAULT_RULES = (
    {
        "stage": models.CRMOpportunityStage.NEW.value,
        "name": "Qualifier le nouveau besoin",
        "delay_days": 1,
        "template_code": "GENERAL_FOLLOW_UP",
    },
    {
        "stage": models.CRMOpportunityStage.QUALIFIED.value,
        "name": "Organiser la prochaine étape",
        "delay_days": 2,
        "template_code": "GENERAL_FOLLOW_UP",
    },
    {
        "stage": models.CRMOpportunityStage.MEASURE_TO_SCHEDULE.value,
        "name": "Planifier la prise de côte",
        "delay_days": 1,
        "template_code": "MEASURE_SCHEDULING",
    },
    {
        "stage": models.CRMOpportunityStage.MEASURE_IN_PROGRESS.value,
        "name": "Suivre le dossier de métré",
        "delay_days": 2,
        "template_code": "GENERAL_FOLLOW_UP",
    },
    {
        "stage": models.CRMOpportunityStage.PROPOSAL_TO_PREPARE.value,
        "name": "Préparer la proposition",
        "delay_days": 1,
        "template_code": "GENERAL_FOLLOW_UP",
    },
    {
        "stage": models.CRMOpportunityStage.PROPOSAL_SENT.value,
        "name": "Relancer la proposition",
        "delay_days": 3,
        "template_code": "PROPOSAL_FOLLOW_UP",
    },
    {
        "stage": models.CRMOpportunityStage.NEGOTIATION.value,
        "name": "Suivre la décision client",
        "delay_days": 2,
        "template_code": "PROPOSAL_FOLLOW_UP",
    },
)

_PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")
_ALLOWED_VARIABLES = {
    "client_name",
    "contact_name",
    "opportunity_reference",
    "opportunity_title",
    "next_milestone",
    "due_date",
    "sender_name",
}


def ensure_default_templates(db):
    expected_codes = {item["code"] for item in DEFAULT_TEMPLATES}
    existing_codes = {
        row[0]
        for row in db.query(models.CRMReminderTemplate.code)
        .filter(models.CRMReminderTemplate.code.in_(expected_codes))
        .all()
    }
    created = False
    for item in DEFAULT_TEMPLATES:
        if item["code"] in existing_codes:
            continue
        db.add(
            models.CRMReminderTemplate(
                **item,
                is_active=True,
                created_by="Système",
            )
        )
        created = True
    if created:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            persisted_codes = {
                row[0]
                for row in db.query(models.CRMReminderTemplate.code)
                .filter(models.CRMReminderTemplate.code.in_(expected_codes))
                .all()
            }
            if not expected_codes.issubset(persisted_codes):
                raise


def ensure_default_rules(db):
    ensure_default_templates(db)
    templates = {
        item.code: item.id
        for item in db.query(models.CRMReminderTemplate)
        .filter(models.CRMReminderTemplate.is_active.is_(True))
        .all()
    }
    expected_stages = {item["stage"] for item in DEFAULT_RULES}
    existing_stages = {
        row[0]
        for row in db.query(models.CRMReminderRule.stage)
        .filter(models.CRMReminderRule.stage.in_(expected_stages))
        .all()
    }
    created = False
    for item in DEFAULT_RULES:
        if item["stage"] in existing_stages:
            continue
        db.add(
            models.CRMReminderRule(
                name=item["name"],
                stage=item["stage"],
                delay_days=item["delay_days"],
                template_id=templates.get(item["template_code"]),
                assignment_strategy="OPPORTUNITY_OWNER",
                is_active=True,
                created_by="Système",
            )
        )
        created = True
    if created:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            persisted_stages = {
                row[0]
                for row in db.query(models.CRMReminderRule.stage)
                .filter(models.CRMReminderRule.stage.in_(expected_stages))
                .all()
            }
            if not expected_stages.issubset(persisted_stages):
                raise


def reminder_plan_key(opportunity, rule):
    entered_at = (
        getattr(opportunity, "stage_entered_at", None)
        or getattr(opportunity, "created_at", None)
        or utcnow()
    )
    stamp = entered_at.strftime("%Y%m%d%H%M%S")
    return f"CRM-PLAN-{opportunity.id}-{rule.id}-{stamp}"


def sync_reminder_plans(db, *, created_by="Système", now=None):
    ensure_default_rules(db)
    now = now or utcnow()
    rules = {
        item.stage: item
        for item in db.query(models.CRMReminderRule)
        .filter(models.CRMReminderRule.is_active.is_(True))
        .all()
    }
    opportunities = (
        db.query(models.CRMOpportunity)
        .filter(
            models.CRMOpportunity.stage.notin_(
                [
                    models.CRMOpportunityStage.WON.value,
                    models.CRMOpportunityStage.LOST.value,
                ]
            )
        )
        .all()
    )
    created = 0
    cancelled = 0
    for opportunity in opportunities:
        pending_plans = (
            db.query(models.CRMReminderPlan)
            .filter(
                models.CRMReminderPlan.opportunity_id == opportunity.id,
                models.CRMReminderPlan.status == "PENDING",
            )
            .all()
        )
        for plan in pending_plans:
            if plan.stage_snapshot != opportunity.stage:
                plan.status = "CANCELLED"
                plan.cancelled_reason = "Étape commerciale modifiée"
                cancelled += 1

        rule = rules.get(opportunity.stage)
        if not rule:
            continue
        key = reminder_plan_key(opportunity, rule)
        if (
            db.query(models.CRMReminderPlan.id)
            .filter(models.CRMReminderPlan.plan_key == key)
            .first()
        ):
            continue
        entered_at = opportunity.stage_entered_at or opportunity.created_at or now
        assigned_user_id = (
            rule.fixed_user_id
            if rule.assignment_strategy == "FIXED_USER"
            else opportunity.owner_user_id
        )
        db.add(
            models.CRMReminderPlan(
                plan_key=key,
                rule_id=rule.id,
                opportunity_id=opportunity.id,
                client_id=opportunity.client_id,
                assigned_user_id=assigned_user_id,
                stage_snapshot=opportunity.stage,
                due_at=entered_at + timedelta(days=rule.delay_days),
                status="PENDING",
                created_by=created_by,
            )
        )
        created += 1
    if created or cancelled:
        db.commit()
    return {"created": created, "cancelled": cancelled}


def reminder_template_code(reminder_kind):
    if reminder_kind == "UNSCHEDULED_MEASURE":
        return "MEASURE_SCHEDULING"
    if reminder_kind in {"OVERDUE_MILESTONE", "STALE_OPPORTUNITY"}:
        return "PROPOSAL_FOLLOW_UP"
    return "GENERAL_FOLLOW_UP"


def build_template_context(client, opportunity=None, *, sender_name="MMG Menuiseries", due_at=None):
    contact_name = (getattr(client, "contact_name", None) or "").strip()
    if not contact_name:
        contact_name = (getattr(client, "name", None) or "Madame, Monsieur").strip()
    due_date = ""
    if due_at:
        if isinstance(due_at, datetime):
            due_date = due_at.strftime("%d/%m/%Y")
        else:
            due_date = str(due_at)
    return {
        "client_name": getattr(client, "name", None) or "Client",
        "contact_name": contact_name,
        "opportunity_reference": (
            getattr(opportunity, "reference", None) if opportunity else None
        ) or "votre dossier",
        "opportunity_title": (
            getattr(opportunity, "title", None) if opportunity else None
        ) or "votre projet",
        "next_milestone": (
            getattr(opportunity, "next_milestone", None) if opportunity else None
        ) or "reprendre contact",
        "due_date": due_date,
        "sender_name": sender_name or "MMG Menuiseries",
    }


def render_template(value, context):
    variables = set(_PLACEHOLDER.findall(value or ""))
    unknown = variables - _ALLOWED_VARIABLES
    if unknown:
        raise ValueError(
            "Variables de modèle non autorisées : " + ", ".join(sorted(unknown))
        )
    rendered = value or ""
    for variable in variables:
        rendered = rendered.replace(f"{{{{{variable}}}}}", str(context.get(variable, "")))
    return rendered


def render_email(template, context):
    subject = render_template(template.subject_template, context).strip()
    message = render_template(template.body_template, context).strip()
    if not subject or not message:
        raise ValueError("Le modèle doit produire un objet et un message non vides.")
    return subject, message


def plain_text_to_html(message):
    paragraphs = [
        f"<p>{escape(block).replace(chr(10), '<br>')}</p>"
        for block in (message or "").split("\n\n")
        if block.strip()
    ]
    return (
        '<html><body style="font-family:Arial,sans-serif;color:#1e293b;line-height:1.55">'
        + "".join(paragraphs)
        + "</body></html>"
    )
