from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from organizations.models import Organization
from regions.models import Region
from usergroups.models import UserGroup

from .models import ResponderLocation


class ResponderLocationModelTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org")
        self.region = Region.objects.create(code="R1", name_ar="المنطقة 1")
        self.ug = UserGroup.objects.create(name_ar="المستجيبين", code="ECRMOBIL", is_mobile_group=True)
        self.user = User.objects.create_user(
            national_id="1000000000",
            full_name="Responder One",
            email="r1@example.com",
            phone="0500000000",
            organization=self.org,
            region=self.region,
            user_group=self.ug,
            password="pass12345",
        )

    def test_create_or_update_location(self):
        obj, created = ResponderLocation.objects.update_or_create(
            responder=self.user,
            defaults={
                "latitude": "24.713600",
                "longitude": "46.675300",
                "last_seen": timezone.now(),
            },
        )
        self.assertTrue(created)
        self.assertEqual(obj.responder_id, self.user.id)
