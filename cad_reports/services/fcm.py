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
    normalized: dict[str, str] = {}
    for k, v in (data or {}).items():
        if v is None:
            continue
        normalized[str(k)] = str(v)
    return normalized


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
                priority="high",
                default_sound=False,
            ),
        )

    return messaging.AndroidConfig(
        priority="high",
        notification=messaging.AndroidNotification(
            channel_id=REPORT_CHANNEL_ID,
            sound=REPORT_SOUND_ANDROID,
            priority="high",
            default_sound=False,
        ),
    )


def _apns_sound_name(notification_type: str) -> str:
    if notification_type == CHAT_TYPE:
        return CHAT_SOUND_IOS
    return REPORT_SOUND_IOS


def _apns_headers(notification_type: str) -> dict[str, str]:
    # iOS يحتاج push-type=alert للإشعارات الظاهرة مع الصوت.
    # priority=10 تعني إرسال فوري.
    # collapse-id اختياري لتنظيم التكرار حسب النوع.
    collapse_id = "cad-chat" if notification_type == CHAT_TYPE else "cad-report"

    return {
        "apns-priority": "10",
        "apns-push-type": "alert",
        "apns-collapse-id": collapse_id,
    }


def _apns_config(messaging, notification_type: str):
    sound_name = _apns_sound_name(notification_type)

    return messaging.APNSConfig(
        headers=_apns_headers(notification_type),
        payload=messaging.APNSPayload(
            aps=messaging.Aps(
                sound=sound_name,
                badge=1,
                content_available=False,
                mutable_content=False,
            )
        ),
    )


def _build_message(
    messaging,
    *,
    token: str,
    title: str,
    body: str,
    payload_data: dict[str, str],
    notification_type: str,
):
    return messaging.Message(
        token=token,
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data=payload_data,
        android=_android_config(messaging, notification_type),
        apns=_apns_config(messaging, notification_type),
    )


def send_fcm_to_tokens(
    tokens: list[str],
    *,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> bool:
    """
    Send visible FCM notifications to multiple device tokens.

    Supports notification types:
    - report
    - chat

    Expected data examples:
    {
        "type": "report",
        "report_id": "123",
        "status": "OPEN",
        "cad_number": "CAD-001",
    }

    {
        "type": "chat",
        "report_id": "123",
        "cad_number": "CAD-001",
        "message": "hello",
        "sender": "Ahmed",
    }
    """
    if not tokens:
        logger.info("FCM: no tokens provided")
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

    # ضمان وجود type دائمًا كي يفهمه Flutter محليًا عند الحاجة.
    payload_data["type"] = notification_type

    ok = False
    unique_tokens = [t for t in dict.fromkeys(tokens) if str(t).strip()]

    for token in unique_tokens:
        try:
            msg = _build_message(
                messaging,
                token=token,
                title=title,
                body=body,
                payload_data=payload_data,
                notification_type=notification_type,
            )
            response = messaging.send(msg)
            logger.info(
                "FCM: sent successfully type=%s token=%s response=%s",
                notification_type,
                token[-12:] if len(token) > 12 else token,
                response,
            )
            ok = True
        except Exception as e:
            logger.exception(
                "FCM: send failed type=%s token=%s error=%s",
                notification_type,
                token[-12:] if len(token) > 12 else token,
                e,
            )
            continue

    return ok