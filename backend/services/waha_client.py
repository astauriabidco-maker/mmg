import json
import logging
import os
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)
_MAX_ACTIVITY_EVENTS = 50
_DEFAULT_TIMEOUT_SECONDS = 15
_ACTIVITY_EVENTS = deque(maxlen=_MAX_ACTIVITY_EVENTS)


@dataclass(frozen=True)
class WahaSettings:
    base_url: str
    api_key: str
    session: str = "default"
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS


def get_waha_settings() -> Optional[WahaSettings]:
    base_url = (os.environ.get("WAHA_BASE_URL") or "").strip()
    api_key = (os.environ.get("WAHA_API_KEY") or "").strip()
    if not base_url or not api_key:
        return None

    return WahaSettings(
        base_url=base_url.rstrip("/") + "/",
        api_key=api_key,
        session=(os.environ.get("WAHA_SESSION") or "default").strip() or "default",
        timeout_seconds=_DEFAULT_TIMEOUT_SECONDS,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_activity(event_type: str, status: str, detail: str, recipient: Optional[str] = None) -> None:
    _ACTIVITY_EVENTS.appendleft(
        {
            "at": _now_iso(),
            "type": event_type,
            "status": status,
            "recipient": recipient,
            "detail": detail,
        }
    )


def get_waha_activity(limit: int = 20) -> list[dict]:
    return list(_ACTIVITY_EVENTS)[: max(1, min(limit, _MAX_ACTIVITY_EVENTS))]


def normalize_waha_chat_id(phone_or_chat_id: str) -> str:
    value = (phone_or_chat_id or "").strip()
    if not value:
        raise ValueError("WhatsApp recipient is required")
    if "@" in value:
        return value
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        raise ValueError("WhatsApp recipient must contain a phone number or chatId")
    return f"{digits}@c.us"


def _waha_request(path: str, settings: WahaSettings, method: str = "GET", payload: Optional[dict] = None) -> dict | list:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        urljoin(settings.base_url, path.lstrip("/")),
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Api-Key": settings.api_key,
        },
        method=method,
    )
    with urllib.request.urlopen(request, timeout=settings.timeout_seconds) as response:
        body = response.read()
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


def get_waha_session_status(settings: Optional[WahaSettings] = None) -> dict:
    settings = settings or get_waha_settings()
    if settings is None:
        return {
            "configured": False,
            "healthy": False,
            "session": None,
            "status": "not_configured",
            "base_url": None,
            "detail": "WAHA_BASE_URL ou WAHA_API_KEY absent.",
            "checked_at": _now_iso(),
            "activity": get_waha_activity(),
        }

    result = {
        "configured": True,
        "healthy": False,
        "session": settings.session,
        "status": "unknown",
        "base_url": settings.base_url.rstrip("/"),
        "detail": None,
        "checked_at": _now_iso(),
        "activity": get_waha_activity(),
    }
    try:
        session_info = _waha_request(f"api/sessions/{settings.session}", settings)
        status = str(session_info.get("status") or "unknown")
        result.update(
            {
                "healthy": status.upper() == "WORKING",
                "status": status,
                "detail": session_info.get("name") or settings.session,
                "session_info": session_info,
            }
        )
        _record_activity("status", "ok", f"Session {settings.session}: {status}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        result.update({"status": "error", "detail": f"HTTP {exc.code}: {body}"})
        _record_activity("status", "error", result["detail"])
    except Exception as exc:
        result.update({"status": "error", "detail": str(exc)})
        _record_activity("status", "error", result["detail"])
    result["activity"] = get_waha_activity()
    return result


def send_waha_text_message(to: str, message: str, settings: Optional[WahaSettings] = None) -> bool:
    settings = settings or get_waha_settings()
    if settings is None:
        return False

    payload = {
        "session": settings.session,
        "chatId": normalize_waha_chat_id(to),
        "text": message,
    }
    try:
        _waha_request("api/sendText", settings, method="POST", payload=payload)
        logger.info("[WAHA] Message WhatsApp envoyé à %s via session %s.", payload["chatId"], settings.session)
        _record_activity("send", "ok", "Message texte envoyé.", payload["chatId"])
        return True
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.error("[WAHA] Échec HTTP %s vers %s: %s", exc.code, payload["chatId"], body)
        _record_activity("send", "error", f"HTTP {exc.code}: {body}", payload["chatId"])
    except Exception as exc:
        logger.error("[WAHA] Échec d'envoi vers %s: %s", payload["chatId"], exc)
        _record_activity("send", "error", str(exc), payload["chatId"])
    return False


def send_waha_test_message(to: str, message: Optional[str] = None) -> dict:
    settings = get_waha_settings()
    if settings is None:
        raise RuntimeError("WAHA n'est pas configuré.")
    text = message or "Test MMG : connexion WAHA opérationnelle."
    success = send_waha_text_message(to, text, settings=settings)
    return {
        "success": success,
        "recipient": normalize_waha_chat_id(to),
        "session": settings.session,
        "activity": get_waha_activity(),
    }
