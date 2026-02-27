from __future__ import annotations

from django.contrib.auth.signals import user_logged_out
from django.dispatch import receiver

from .models import ResponderLocation


@receiver(user_logged_out)
def purge_location_on_logout(sender, request, user, **kwargs):
    """Ensure responder location is removed on ANY Django logout (admin/web/etc)."""
    if user is None:
        return
    ResponderLocation.objects.filter(responder=user).delete()
