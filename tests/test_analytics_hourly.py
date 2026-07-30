from datetime import datetime

from backend import models
from backend.core.security import get_password_hash


def _admin_headers(client, TestingSessionLocal):
    with TestingSessionLocal() as db:
        db.add(
            models.User(
                username="analytics-admin",
                pin_hash=get_password_hash("1234"),
                role="ADMIN",
                is_active=True,
            )
        )
        db.add_all(
            [
                models.ProductionLog(
                    station="PVC_DEBIT",
                    material="PVC",
                    start_time=datetime(2026, 7, 30, 8, 15),
                ),
                models.ProductionLog(
                    station="PVC_DEBIT",
                    material="PVC",
                    start_time=datetime(2026, 7, 30, 8, 45),
                ),
                models.ProductionLog(
                    station="ALU_DEBIT",
                    material="ALU",
                    start_time=datetime(2026, 7, 30, 11, 5),
                ),
            ]
        )
        db.commit()

    response = client.post(
        "/token",
        data={"username": "analytics-admin", "password": "1234"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_hourly_analytics_uses_portable_hour_extraction(
    isolated_client,
    monkeypatch,
):
    client, TestingSessionLocal = isolated_client
    headers = _admin_headers(client, TestingSessionLocal)
    monkeypatch.setattr(
        "backend.routers.v2_analytics.utcnow",
        lambda: datetime(2026, 7, 30, 12, 0),
    )

    response = client.get("/v2/analytics/hourly", headers=headers)

    assert response.status_code == 200, response.text
    by_hour = {item["name"]: item["count"] for item in response.json()}
    assert by_hour["8:00"] == 2
    assert by_hour["11:00"] == 1
    assert by_hour["9:00"] == 0
