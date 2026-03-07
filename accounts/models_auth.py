# accounts/models_auth.py
"""
Compatibility shim:
هذا الملف موجود فقط لتفادي كسر الاستيرادات القديمة مثل:
from accounts.models_auth import EmailOTP, EmailVerification

⚠️ ممنوع تعريف موديلات Django هنا، لأن ذلك يسبب تعارض (Conflicting models)
مع الموديلات الموجودة في accounts/models.py.
"""

from .models import EmailOTP, EmailVerification

__all__ = ["EmailOTP", "EmailVerification"]