from __future__ import annotations

import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.exceptions import ObjectDoesNotExist

from cad_reports.models import CADReport, CADReportActivity

logger = logging.getLogger(__name__)

def _actor_name(user) -> str:
    """Return a safe display name for custom User models that may not have `username`."""
    if not user:
        return "النظام"
    # Prefer explicit display fields if present
    for attr in ("full_name", "name", "display_name"):
        v = getattr(user, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # Django's standard helpers
    try:
        v = user.get_full_name()
        if isinstance(v, str) and v.strip():
            return v.strip()
    except Exception:
        pass
    # get_username exists even if `username` field doesn't
    try:
        v = user.get_username()
        if isinstance(v, str) and v.strip():
            return v.strip()
    except Exception:
        pass
    # common identifiers
    for attr in ("email", "phone", "phone_number", "mobile"):
        v = getattr(user, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return str(user)



class ReportConsumer(AsyncWebsocketConsumer):
    """
    WS: /ws/cad/<report_id>/

    يدعم:
    - إنشاء رسالة: {"message": "..."}
    - جلب السجل: {"type": "history", "limit": 80}
    """

    async def connect(self):
        self.report_id = str(self.scope["url_route"]["kwargs"]["report_id"])
        self.group_name = f"cad_report_{self.report_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # ✅ أرسل السجل مباشرة عند فتح الاتصال
        try:
            items = await self.get_history(limit=80)
            await self.send(text_data=json.dumps({"type": "history", "items": items}))
        except Exception as exc:
            logger.exception("WS history failed: %s", exc)
            await self.send(text_data=json.dumps({"type": "history", "items": []}))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data: str):
        # Parse JSON
        try:
            payload = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({"type": "error", "detail": "Invalid JSON."}))
            return

        msg_type = str(payload.get("type") or "").lower()

        # ===== History =====
        if msg_type == "history":
            limit = payload.get("limit", 80)
            try:
                limit = int(limit)
            except Exception:
                limit = 80
            limit = max(1, min(limit, 200))

            try:
                items = await self.get_history(limit=limit)
                await self.send(text_data=json.dumps({"type": "history", "items": items}))
            except Exception as exc:
                logger.exception("WS history failed: %s", exc)
                await self.send(text_data=json.dumps({"type": "error", "detail": "Failed to load history."}))
            return

        # ===== Create message =====
        raw_message = payload.get("message", "")
        if raw_message is None:
            raw_message = ""
        message = str(raw_message).strip()

        # ✅ أهم سطر: لا تسمح بـ None نهائيًا + لا تحفظ فراغ
        if not message:
            await self.send(text_data=json.dumps({"type": "error", "detail": "Message is required."}))
            return

        user = self.scope.get("user")

        try:
            activity = await self.create_activity(user, message)
        except ObjectDoesNotExist:
            await self.send(text_data=json.dumps({"type": "error", "detail": "Report not found."}))
            return
        except Exception as exc:
            logger.exception("WS create_activity failed: %s", exc)
            await self.send(text_data=json.dumps({"type": "error", "detail": "Server error."}))
            return

        username = getattr(user, "username", None) if getattr(user, "is_authenticated", False) else "—"

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat_message",
                "kind": activity.kind,
                "action": activity.action,
                "message": activity.message,
                "username": username,
                "timestamp": activity.created_at.isoformat(),
            },
        )

    @database_sync_to_async
    def create_activity(self, user, message: str) -> CADReportActivity:
        report = CADReport.objects.get(pk=self.report_id)
        return CADReportActivity.objects.create(
            report=report,
            user=user if getattr(user, "is_authenticated", False) else None,
            kind=CADReportActivity.Kind.MESSAGE,
            action=CADReportActivity.Action.NOTE,
            message=message,  # ✅ string فقط
        )

    @database_sync_to_async
    def get_history(self, limit: int = 80):
        try:
            limit = int(limit)
        except Exception:
            limit = 80
        limit = max(1, min(limit, 200))

        try:
            qs = (
                CADReportActivity.objects
                .filter(report_id=self.report_id)   # ✅ بدون CADReport.objects.get
                .select_related("user")
                .order_by("-created_at")[:limit]
            )

            items = []
            for a in reversed(list(qs)):
                items.append({
                    "kind": getattr(a, "kind", "message"),
                    "action": getattr(a, "action", "note"),
                    "message": a.message or "",
                    "created_at": a.created_at.isoformat() if getattr(a, "created_at", None) else "",
                    "actor_name": (_actor_name(a.user) if getattr(a, "user_id", None) else "النظام"),
                })
            return items

        except Exception as exc:
            logger.exception("get_history failed report_id=%s: %s", self.report_id, exc)
            return []  # ✅ لا ترسل error، فقط رجّع فاضي
        
    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))