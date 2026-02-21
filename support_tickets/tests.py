from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from django.utils import timezone

from .models import (
    SupportTicket,
    TicketSource,
    TicketMainCategory,
    TicketSubCategory,
    TicketPause,
    PauseReason,
    TicketComment,
    TicketStatus,
)

User = get_user_model()


class TicketCodeTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user(username="u1", password="x")

        self.main_inc = TicketMainCategory.objects.create(kind="INC", name="الأعطال", sla_minutes=60)
        self.sub_inc = TicketSubCategory.objects.create(main_category=self.main_inc, name="عطل في التطبيق")

        self.main_req = TicketMainCategory.objects.create(kind="REQ", name="الطلبات", sla_minutes=60)
        self.sub_req = TicketSubCategory.objects.create(main_category=self.main_req, name="طلب صلاحية")

    def test_inc_web_prefix_inc(self):
        t = SupportTicket(
            requester=self.u,
            source=TicketSource.WEB,
            main_category=self.main_inc,
            sub_category=self.sub_inc,
            description="x",
        )
        t.full_clean()
        t.ensure_code()
        self.assertTrue(t.code.startswith("INC"))
        self.assertEqual(len(t.code), 3 + 8)

    def test_inc_mobile_prefix_ecr(self):
        t = SupportTicket(
            requester=self.u,
            source=TicketSource.MOBILE,
            main_category=self.main_inc,
            sub_category=self.sub_inc,
            description="x",
        )
        t.full_clean()
        t.ensure_code()
        self.assertTrue(t.code.startswith("ECR"))
        self.assertEqual(len(t.code), 3 + 8)

    def test_req_prefix_req(self):
        t = SupportTicket(
            requester=self.u,
            source=TicketSource.WEB,
            main_category=self.main_req,
            sub_category=self.sub_req,
            description="x",
        )
        t.full_clean()
        t.ensure_code()
        self.assertTrue(t.code.startswith("REQ"))
        self.assertEqual(len(t.code), 3 + 8)


class TicketTimingTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user(username="u1", password="x")
        self.main_inc = TicketMainCategory.objects.create(kind="INC", name="الأعطال", sla_minutes=60)
        self.sub_inc = TicketSubCategory.objects.create(main_category=self.main_inc, name="عطل في التطبيق")

    def test_pause_excluded_from_resolution(self):
        t = SupportTicket.objects.create(
            requester=self.u,
            source=TicketSource.WEB,
            main_category=self.main_inc,
            sub_category=self.sub_inc,
            description="x",
        )

        # ضبط أوقات مصطنعة
        start = timezone.now() - timedelta(hours=2)
        t.created_at = start
        t.deadline_at = start + timedelta(minutes=t.sla_minutes)
        t.save(update_fields=["created_at", "deadline_at"])

        # Pause لمدة 30 دقيقة
        p = TicketPause.objects.create(ticket=t, reason=PauseReason.ASK_REQUESTER, started_at=start + timedelta(minutes=30))
        p.ended_at = start + timedelta(minutes=60)
        p.save(update_fields=["ended_at"])

        # إغلاق بعد 120 دقيقة من الإنشاء
        t.closed_at = start + timedelta(minutes=120)
        t.status = TicketStatus.CLOSED
        t.save(update_fields=["closed_at", "status"])

        # raw = 120min, paused = 30min => effective 90min
        self.assertEqual(t.resolution_time_seconds(), 90 * 60)

    def test_first_support_reply_sets_first_response(self):
        t = SupportTicket.objects.create(
            requester=self.u,
            source=TicketSource.WEB,
            main_category=self.main_inc,
            sub_category=self.sub_inc,
            description="x",
        )

        self.assertIsNone(t.first_response_at)
        TicketComment.objects.create(ticket=t, author=self.u, body="رد دعم", is_support_reply=True)

        t.refresh_from_db()
        self.assertIsNotNone(t.first_response_at)
        self.assertEqual(t.status, TicketStatus.IN_PROGRESS)


class TicketSLATests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user(username="u1", password="x")
        self.main_inc = TicketMainCategory.objects.create(kind="INC", name="الأعطال", sla_minutes=60)
        self.sub_inc = TicketSubCategory.objects.create(main_category=self.main_inc, name="عطل في التطبيق")

    def test_overdue_without_pause_stop_policy(self):
        t = SupportTicket.objects.create(
            requester=self.u,
            source=TicketSource.WEB,
            main_category=self.main_inc,
            sub_category=self.sub_inc,
            description="x",
        )

        start = timezone.now() - timedelta(hours=3)
        t.created_at = start
        t.sla_minutes = 60
        t.deadline_at = start + timedelta(minutes=60)
        t.save(update_fields=["created_at", "sla_minutes", "deadline_at"])

        # بعد 2 ساعة من الإنشاء => متأخر (لأن SLA 60 دقيقة)
        at = start + timedelta(minutes=120)
        self.assertTrue(t.is_overdue(at=at))

    @override_settings(SUPPORT_TICKETS_SLA_STOP_DURING_PAUSE=True)
    def test_pause_stop_policy_extends_deadline(self):
        t = SupportTicket.objects.create(
            requester=self.u,
            source=TicketSource.WEB,
            main_category=self.main_inc,
            sub_category=self.sub_inc,
            description="x",
        )

        start = timezone.now() - timedelta(hours=3)
        t.created_at = start
        t.sla_minutes = 60
        t.deadline_at = start + timedelta(minutes=60)
        t.save(update_fields=["created_at", "sla_minutes", "deadline_at"])

        # Pause 90 دقيقة تبدأ بعد 10 دقائق
        p = TicketPause.objects.create(
            ticket=t,
            reason=PauseReason.ASK_REQUESTER,
            started_at=start + timedelta(minutes=10),
            ended_at=start + timedelta(minutes=100),
        )

        at = start + timedelta(minutes=120)
        # بدون تمديد: متأخر. مع تمديد 90 دقيقة: لا.
        self.assertFalse(t.is_overdue(at=at))


class DashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="normal", password="x")
        self.support = User.objects.create_user(username="support", password="x")

        # create SUPPORT group if not exists
        from django.contrib.auth.models import Group
        g, _ = Group.objects.get_or_create(name="SUPPORT")
        self.support.groups.add(g)

        self.main_inc = TicketMainCategory.objects.create(kind="INC", name="الأعطال", sla_minutes=60)
        self.sub_inc = TicketSubCategory.objects.create(main_category=self.main_inc, name="عطل عام")

        # create a ticket
        self.t = SupportTicket.objects.create(
            requester=self.user,
            source=TicketSource.WEB,
            main_category=self.main_inc,
            sub_category=self.sub_inc,
            description="x",
        )

    def test_dashboard_forbidden_for_normal_user(self):
        self.client.login(username="normal", password="x")
        resp = self.client.get("/support_tickets/dashboard/")
        self.assertIn(resp.status_code, (403, 302))

    def test_dashboard_ok_for_support(self):
        self.client.login(username="support", password="x")
        resp = self.client.get("/support_tickets/dashboard/")
        self.assertEqual(resp.status_code, 200)

    def test_api_dashboard_summary_ok_for_support(self):
        self.client.login(username="support", password="x")
        resp = self.client.get("/support_tickets/api/dashboard/summary/?days=30")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("ok"))



from django.urls import reverse
from django.contrib.auth.models import Group


class TicketAPITests(TestCase):
    def setUp(self):
        self.requester = User.objects.create_user(username="req", password="x")
        self.support = User.objects.create_user(username="sup", password="x")
        Group.objects.get_or_create(name="SUPPORT")
        self.support.groups.add(Group.objects.get(name="SUPPORT"))

        self.main_inc = TicketMainCategory.objects.create(kind="INC", name="الأعطال", sla_minutes=60)
        self.sub_inc = TicketSubCategory.objects.create(main_category=self.main_inc, name="عطل شبكة")

    def test_api_create_and_list(self):
        self.client.login(username="req", password="x")
        create_url = reverse("support_tickets:api_tickets_create")
        resp = self.client.post(create_url, data={
            "kind": "INC",
            "main_category": self.main_inc.id,
            "sub_category": self.sub_inc.id,
            "description": "test",
        })
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()["ok"])
        tid = resp.json()["ticket"]["id"]

        list_url = reverse("support_tickets:api_tickets_list")
        resp2 = self.client.get(list_url)
        self.assertEqual(resp2.status_code, 200)
        data = resp2.json()
        self.assertTrue(any(x["id"] == tid for x in data["results"]))

    def test_api_support_pause_resume_close(self):
        t = SupportTicket.objects.create(
            requester=self.requester,
            source=TicketSource.WEB,
            main_category=self.main_inc,
            sub_category=self.sub_inc,
            description="x",
        )
        self.client.login(username="sup", password="x")

        pause_url = reverse("support_tickets:api_ticket_pause", kwargs={"pk": t.pk})
        resp = self.client.post(pause_url, data={"reason": PauseReason.ASK_REQUESTER})
        self.assertEqual(resp.status_code, 200)
        t.refresh_from_db()
        self.assertEqual(t.status, TicketStatus.PAUSED)

        resume_url = reverse("support_tickets:api_ticket_resume", kwargs={"pk": t.pk})
        resp2 = self.client.post(resume_url)
        self.assertEqual(resp2.status_code, 200)
        t.refresh_from_db()
        self.assertEqual(t.status, TicketStatus.IN_PROGRESS)

        close_url = reverse("support_tickets:api_ticket_close", kwargs={"pk": t.pk})
        resp3 = self.client.post(close_url, data={"closing_note": "done"})
        self.assertEqual(resp3.status_code, 200)
        t.refresh_from_db()
        self.assertEqual(t.status, TicketStatus.CLOSED)
