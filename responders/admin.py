from django.contrib import admin

from .models import ResponderLocation


@admin.register(ResponderLocation)
class ResponderLocationAdmin(admin.ModelAdmin):
    list_display = (
        "responder",
        "latitude",
        "longitude",
        "accuracy_m",
        "last_seen",
        "updated_at",
    )
    search_fields = ("responder__full_name", "responder__national_id", "responder__email")
    list_filter = ("platform",)
    readonly_fields = ("updated_at",)
