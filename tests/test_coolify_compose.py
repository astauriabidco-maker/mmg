from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COOLIFY_COMPOSE = ROOT / "docker-compose.coolify.yml"


def _backend_environment_block() -> str:
    content = COOLIFY_COMPOSE.read_text(encoding="utf-8")
    backend = content.split("  backend:\n", maxsplit=1)[1]
    environment = backend.split("    environment:\n", maxsplit=1)[1]
    return environment.split("    depends_on:\n", maxsplit=1)[0]


def test_coolify_backend_receives_crm_and_transactional_smtp_environment():
    environment = _backend_environment_block()
    expected_variables = {
        "CRM_REMINDERS_ENABLED",
        "CRM_REMINDER_SYNC_INTERVAL_SECONDS",
        "CRM_SMTP_REQUIRED",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "SMTP_FROM",
        "SMTP_USE_TLS",
        "PURCHASES_CC_EMAIL",
    }

    for variable in expected_variables:
        assert f"      {variable}:" in environment

    assert "SMTP_PORT: ${SMTP_PORT:-587}" in environment
