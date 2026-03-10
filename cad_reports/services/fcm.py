from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


REPORT_TYPE = "report"
CHAT_TYPE = "chat"

REPORT_CHANNEL_ID = "ecr_report_channel"
CHAT_CHANNEL_ID = "ecr_chat_channel"

REPORT_SOUND_ANDROID = "notification_sound"
CHAT_SOUND_ANDROID = "newchat"

REPORT_SOUND_IOS = "notification_sound.aiff"
CHAT_SOUND_IOS = "newchat.aiff"


def _enabled() -> bool:
    return bool(getattr(settings, "FCM_ENABLED", False))


def _get_firebase():
    try:
        import firebase_admin
        from firebase_admin import credentials, messaging
        return firebase_admin, credentials, messaging
    except Exception as e:
        logger.warning("FCM: firebase_admin not installed (%s)", e)
        return None, None, None


def _init_firebase(firebase_admin, credentials) -> bool:
    try:
        if not firebase_admin._apps:
            cred_path = getattr(settings, "FCM_SERVICE_ACCOUNT_FILE", None)
            if not cred_path:
                logger.warning("FCM: missing settings.FCM_SERVICE_ACCOUNT_FILE")
                return False
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        return True
    except Exception:
        logger.exception("FCM: init failed")
        return False


def _normalize_data(data: dict[str, Any] | None) -> dict[str, str]:
    return {str(k): str(v) for k, v in (data or {}).items() if v is not None}


def _resolve_type(payload_data: dict[str, str]) -> str:
    raw_type = (payload_data.get("type") or "").strip().lower()
    if raw_type == CHAT_TYPE:
        return CHAT_TYPE
    return REPORT_TYPE


def _android_config(messaging, notification_type: str):
    if notification_type == CHAT_TYPE:
        return messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                channel_id=CHAT_CHANNEL_ID,
                sound=CHAT_SOUND_ANDROID,
            ),
        )

    return messaging.AndroidConfig(
        priority="high",
        notification=messaging.AndroidNotification(
            channel_id=REPORT_CHANNEL_ID,
            sound=REPORT_SOUND_ANDROID,
        ),
    )


def _apns_config(messaging, notification_type: str):
    sound_name = CHAT_SOUND_IOS if notification_type == CHAT_TYPE else REPORT_SOUND_IOS

    return messaging.APNSConfig(
        headers={
            "apns-priority": "10",
        },
        payload=messaging.APNSPayload(
            aps=messaging.Aps(
                sound=sound_name,
                badge=1,
                content_available=True,
            )
        ),
    )


def send_fcm_to_tokens(
    tokens: list[str],
    *,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> bool:
    """
    Send FCM message to a list of device tokens.

    Supports:
    - report notifications
    - chat notifications

    Expected `data` examples:
    {
        "type": "report",
        "report_id": "123",
        "status": "new",
    }

    {
        "type": "chat",
        "report_id": "123",
        "chat_id": "999",
    }
    """
    if not tokens:
        return False

    if not _enabled():
        logger.info("FCM: disabled by settings")
        return False

    firebase_admin, credentials, messaging = _get_firebase()
    if not firebase_admin or not credentials or not messaging:
        return False

    if not _init_firebase(firebase_admin, credentials):
        return False

    payload_data = _normalize_data(data)
    notification_type = _resolve_type(payload_data)

    # تأكد أن النوع موجود دائمًا ليفهمه Flutter
    payload_data["type"] = notification_type

    android_config = _android_config(messaging, notification_type)
    apns_config = _apns_config(messaging, notification_type)

    ok = False

    for token in tokens:
        try:
            msg = messaging.Message(
                token=token,
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=payload_data,
                android=android_config,
                apns=apns_config,
            )
            messaging.send(msg)
            ok = True
        except Exception:
            logger.exception("FCM: send failed for token=%s", token)
            continue

    return ok