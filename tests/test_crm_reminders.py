import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import models, schemas
from backend.database import Base
from backend.routers import v2_mmg
from backend.services.crm_reminders import (
    build_template_context,
    ensure_default_templates,
    plain_text_to_html,
    render_email,
    render_template,
)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def crm_records(db):
    client = models.Client(
        name="Client Relance",
        contact_name="Mme Martin",
        email="client@example.test",
    )
    db.add(client)
    db.flush()
    opportunity = models.CRMOpportunity(
        reference="OPP-TEST-RELANCE",
        client_id=client.id,
        title="Remplacement des menuiseries",
        stage=models.CRMOpportunityStage.PROPOSAL_SENT.value,
        probability=60,
        next_milestone="Valider la proposition",
        created_by="commercial",
    )
    db.add(opportunity)
    db.commit()
    return client, opportunity


def test_default_templates_render_controlled_variables(db, crm_records):
    client, opportunity = crm_records
    ensure_default_templates(db)

    templates = db.query(models.CRMReminderTemplate).all()
    assert {item.code for item in templates} == {
        "GENERAL_FOLLOW_UP",
        "MEASURE_SCHEDULING",
        "PROPOSAL_FOLLOW_UP",
    }

    template = next(item for item in templates if item.code == "PROPOSAL_FOLLOW_UP")
    subject, message = render_email(
        template,
        build_template_context(client, opportunity, sender_name="alice"),
    )
    assert "OPP-TEST-RELANCE" in subject
    assert "Mme Martin" in message
    assert "alice" in message


def test_template_rejects_unknown_variables_and_html_is_escaped():
    with pytest.raises(ValueError, match="non autorisées"):
        render_template("Bonjour {{password}}", {})

    html = plain_text_to_html("Bonjour <script>\nMerci")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<br>" in html


def test_send_requires_explicit_confirmation(db, crm_records):
    client, opportunity = crm_records
    item = schemas.CRMReminderSendRequest(
        client_id=client.id,
        opportunity_id=opportunity.id,
        recipient=client.email,
        subject="Relance",
        message="Bonjour",
        confirm_send=False,
    )

    with pytest.raises(HTTPException) as exc:
        v2_mmg.send_crm_reminder(
            item,
            db=db,
            current_user={"sub": "alice"},
        )
    assert exc.value.status_code == 409
    assert db.query(models.CRMReminderDelivery).count() == 0


def test_skipped_send_is_logged_without_fake_activity(
    db,
    crm_records,
    monkeypatch,
):
    client, opportunity = crm_records
    monkeypatch.setattr(v2_mmg, "_send_smtp_email", lambda *args, **kwargs: False)
    item = schemas.CRMReminderSendRequest(
        reminder_key="stale-1",
        client_id=client.id,
        opportunity_id=opportunity.id,
        recipient=client.email,
        subject="Relance",
        message="Bonjour",
        confirm_send=True,
    )

    result = v2_mmg.send_crm_reminder(
        item,
        db=db,
        current_user={"sub": "alice"},
    )

    assert result["status"] == "SKIPPED"
    assert "SMTP non configuré" in result["error_message"]
    assert db.query(models.CRMReminderDelivery).count() == 1
    assert db.query(models.CRMActivity).count() == 0


def test_successful_send_creates_email_activity(
    db,
    crm_records,
    monkeypatch,
):
    client, opportunity = crm_records
    monkeypatch.setattr(v2_mmg, "_send_smtp_email", lambda *args, **kwargs: True)
    item = schemas.CRMReminderSendRequest(
        client_id=client.id,
        opportunity_id=opportunity.id,
        recipient=client.email,
        subject="Relance proposition",
        message="Bonjour Mme Martin",
        confirm_send=True,
    )

    result = v2_mmg.send_crm_reminder(
        item,
        db=db,
        current_user={"sub": "alice"},
    )

    assert result["status"] == "SENT"
    assert result["sent_at"] is not None
    activity = db.query(models.CRMActivity).one()
    assert activity.activity_type == models.CRMActivityType.EMAIL.value
    assert activity.status == models.CRMActivityStatus.COMPLETED.value
    assert result["activity_id"] == activity.id
