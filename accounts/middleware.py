# accounts/middleware.py
from django.utils.deprecation import MiddlewareMixin
from django.utils.cache import add_never_cache_headers

class NoCacheForAuthenticatedMiddleware(MiddlewareMixin):
    """
    يمنع تخزين صفحات المستخدم المسجّل (أو الصفحات الحساسة) في كاش المتصفح.
    هذا يحل مشكلة الرجوع للخلف بعد logout.
    """
    def process_response(self, request, response):
        try:
            user = getattr(request, "user", None)
            if user is not None and user.is_authenticated:
                add_never_cache_headers(response)
                # زيادة صرامة
                response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                response["Pragma"] = "no-cache"
                response["Expires"] = "0"
        except Exception:
            # لا نكسر الاستجابة في حال أي خطأ
            pass
        return response