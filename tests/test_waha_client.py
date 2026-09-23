import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.waha_client import (  # noqa: E402
    WahaSettings,
    get_waha_settings,
    normalize_waha_chat_id,
    send_waha_text_message,
)


def test_get_waha_settings_requires_base_url_and_api_key(monkeypatch):
    monkeypatch.delenv("WAHA_BASE_URL", raising=False)
    monkeypatch.delenv("WAHA_API_KEY", raising=False)

    assert get_waha_settings() is None

    monkeypatch.setenv("WAHA_BASE_URL", "https://waha.example.test")
    assert get_waha_settings() is None

    monkeypatch.setenv("WAHA_API_KEY", "secret")
    settings = get_waha_settings()
    assert settings is not None
    assert settings.base_url == "https://waha.example.test/"
    assert settings.session == "default"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+33 6 12 34 56 78", "33612345678@c.us"),
        ("33612345678", "33612345678@c.us"),
        ("33612345678@c.us", "33612345678@c.us"),
    ],
)
def test_normalize_waha_chat_id(raw, expected):
    assert normalize_waha_chat_id(raw) == expected


def test_normalize_waha_chat_id_rejects_empty_value():
    with pytest.raises(ValueError):
        normalize_waha_chat_id("")


def test_send_waha_text_message_posts_expected_payload(monkeypatch):
    captured = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"success": true}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setenv("WAHA_LINK_PREVIEW", "true")
    settings = WahaSettings(
        base_url="https://waha.example.test/",
        api_key="secret-key",
        session="mmg-prod",
        timeout_seconds=7,
    )

    with patch("backend.services.waha_client.urllib.request.urlopen", fake_urlopen):
        assert send_waha_text_message("+33 6 12 34 56 78", "Bonjour", settings=settings) is True

    assert captured["url"] == "https://waha.example.test/api/sendText"
    assert captured["headers"]["X-api-key"] == "secret-key"
    assert captured["headers"]["Content-type"] == "application/json"
    assert captured["payload"] == {
        "session": "mmg-prod",
        "chatId": "33612345678@c.us",
        "text": "Bonjour",
        "linkPreview": True,
    }
    assert captured["timeout"] == 7
