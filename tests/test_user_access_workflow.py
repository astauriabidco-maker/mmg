from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import database, models
from backend.core import security
from backend.main import app


def _auth_headers(session_factory, username: str = "user-admin", role: str = "ADMIN") -> dict:
    with session_factory() as db:
        if not db.query(models.User).filter(models.User.username == username).first():
            db.add(models.User(username=username, pin_hash="test-pin", role=role, is_active=True))
            db.commit()
    token = security.create_access_token({"sub": username, "role": role})
    return {"Authorization": f"Bearer {token}"}


def _client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = override_get_db
    return TestClient(app), TestingSessionLocal, engine


def test_create_workshop_user_generates_temporary_pin_and_station_scope():
    client, TestingSessionLocal, engine = _client()
    try:
        headers = _auth_headers(TestingSessionLocal)
        with TestingSessionLocal() as db:
            station = models.Station(code="ALU_DEBIT", display_name="Débit ALU", material=models.MaterialType.ALU, order_index=1)
            db.add(station)
            db.commit()

        response = client.post(
            "/v2/config/users",
            headers=headers,
            json={
                "username": "atelier-debit",
                "first_name": "Awa",
                "last_name": "Debit",
                "role": "MAGASINIER",
                "access_mode": "PIN",
                "station_codes": ["ALU_DEBIT"],
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["temporary_pin"].isdigit()
        assert len(payload["temporary_pin"]) == 4
        assert payload["user"]["access_mode"] == "PIN"
        assert payload["user"]["pin_must_change"] is True
        assert payload["user"]["stations"][0]["code"] == "ALU_DEBIT"
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_email_invitation_requires_email_and_returns_invite_link():
    client, TestingSessionLocal, engine = _client()
    try:
        headers = _auth_headers(TestingSessionLocal)
        missing_email = client.post(
            "/v2/config/users",
            headers=headers,
            json={
                "username": "buyer-no-email",
                "role": "ACHATS",
                "access_mode": "EMAIL",
                "send_invite": True,
            },
        )
        assert missing_email.status_code == 400

        response = client.post(
            "/v2/config/users",
            headers=headers,
            json={
                "username": "buyer-email",
                "first_name": "Binta",
                "email": "binta@example.test",
                "role": "ACHATS",
                "access_mode": "EMAIL",
                "send_invite": True,
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["invitation_sent"] is True
        assert payload["invitation_link"].startswith("INVITE-TOKEN:")
        assert payload["user"]["invitation_status"] == "PENDING"
        assert payload["user"]["email"] == "binta@example.test"
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_resend_user_invitation_regenerates_link():
    client, TestingSessionLocal, engine = _client()
    try:
        headers = _auth_headers(TestingSessionLocal)
        create_response = client.post(
            "/v2/config/users",
            headers=headers,
            json={
                "username": "commercial-invite",
                "email": "commercial@example.test",
                "role": "SALES",
                "access_mode": "EMAIL",
                "send_invite": True,
            },
        )
        user_id = create_response.json()["user"]["id"]
        first_link = create_response.json()["invitation_link"]

        resend_response = client.post(f"/v2/config/users/{user_id}/invite", headers=headers)

        assert resend_response.status_code == 200, resend_response.text
        assert resend_response.json()["invitation_link"] != first_link
        assert resend_response.json()["user"]["invitation_status"] == "PENDING"
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)


def test_invitation_link_prefill_and_login_activation():
    client, TestingSessionLocal, engine = _client()
    try:
        headers = _auth_headers(TestingSessionLocal)
        create_response = client.post(
            "/v2/config/users",
            headers=headers,
            json={
                "username": "invite-activation",
                "email": "invite@example.test",
                "role": "SALES",
                "access_mode": "EMAIL",
                "pin": "Invite-Temp-2026",
                "send_invite": True,
            },
        )
        payload = create_response.json()
        token = payload["invitation_link"].replace("INVITE-TOKEN:", "")

        invite_response = client.get(f"/invitations/{token}")
        assert invite_response.status_code == 200, invite_response.text
        assert invite_response.json()["username"] == "invite-activation"

        login_response = client.post(
            "/token",
            data={"username": "invite-activation", "password": "Invite-Temp-2026"},
        )
        assert login_response.status_code == 200, login_response.text

        expired_invite_response = client.get(f"/invitations/{token}")
        assert expired_invite_response.status_code == 404
        with TestingSessionLocal() as db:
            user = db.query(models.User).filter(models.User.username == "invite-activation").one()
            assert user.invitation_status == "ACTIVE"
            assert user.invite_token is None
            assert user.last_login_at is not None
    finally:
        app.dependency_overrides.pop(database.get_db, None)
        models.Base.metadata.drop_all(bind=engine)
