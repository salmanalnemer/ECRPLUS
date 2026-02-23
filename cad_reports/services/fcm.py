from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return bool(getattr(settings, "FCM_ENABLED", False))


def send_fcm_to_tokens(tokens: list[str], *, title: str, body: str, data: dict[str, Any] | None = None) -> bool:
    """Send FCM message to a list of device tokens.

    Implementation uses firebase_admin if installed & configured.
    Safe: if not configured, it will just log and return False.
    """
    if not tokens:
        return False
    if not _enabled():
        return False

    try:
        import firebase_admin
        from firebase_admin import credentials, messaging
    except Exception as e:
        logger.warning("FCM: firebase_admin not installed (%s)", e)
        return False

    try:
        if not firebase_admin._apps:
            cred_path = getattr(settings, "FCM_SERVICE_ACCOUNT_FILE", None)
            if not cred_path:
                logger.warning("FCM: missing settings.FCM_SERVICE_ACCOUNT_FILE")
                return False
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
    except Exception:
        logger.exception("FCM: init failed")
        return False

    ok = False
    payload_data = {str(k): str(v) for k, v in (data or {}).items() if v is not None}

    for t in tokens:
        try:
            msg = messaging.Message(
                token=t,
                notification=messaging.Notification(title=title, body=body),
                data=payload_data,
            )
            messaging.send(msg)
            ok = True
        except Exception:
            logger.exception("FCM: send failed for token")
            continue
    return ok
