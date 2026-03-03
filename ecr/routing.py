from django.urls import re_path
from cad_reports.consumers import ReportConsumer

websocket_urlpatterns = [
    re_path(r"ws/cad/(?P<report_id>\d+)/$", ReportConsumer.as_asgi()),
    
]