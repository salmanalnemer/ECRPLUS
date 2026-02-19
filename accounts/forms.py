from django import forms
from django.contrib.auth.password_validation import validate_password


class LoginForm(forms.Form):
    identifier = forms.CharField(
        label="رقم الهوية أو البريد الإلكتروني",
        max_length=255,
        widget=forms.TextInput(attrs={"autocomplete": "username", "class": "form-control"}),
    )
    password = forms.CharField(
        label="كلمة المرور",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "class": "form-control"}),
    )


class OTPForm(forms.Form):
    otp = forms.CharField(
        label="رمز التحقق",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "class": "form-control"}),
    )


class ForgotPasswordRequestForm(forms.Form):
    identifier = forms.CharField(
        label="رقم الهوية أو البريد الإلكتروني",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )


class ResetPasswordForm(forms.Form):
    new_password1 = forms.CharField(
        label="كلمة المرور الجديدة",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )
    new_password2 = forms.CharField(
        label="تأكيد كلمة المرور الجديدة",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("new_password1")
        p2 = cleaned.get("new_password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("كلمتا المرور غير متطابقتين.")
        if p1:
            validate_password(p1)
        return cleaned
