import re
from datetime import datetime
from html import escape

from .. import models


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
    existing_codes = {
        row[0]
        for row in db.query(models.CRMReminderTemplate.code)
        .filter(models.CRMReminderTemplate.code.in_([item["code"] for item in DEFAULT_TEMPLATES]))
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
        db.commit()


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
