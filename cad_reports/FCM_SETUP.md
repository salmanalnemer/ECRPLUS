# FCM Background Alerts (CAD Mobile)

## 1) Flutter
### ملفات Firebase (إجباري)
ضع الملفات من Firebase Console:

- Android: `android/app/google-services.json`
- iOS: `ios/Runner/GoogleService-Info.plist`

### تشغيل
```bash
flutter pub get
flutter run
```

## 2) Django (cad_reports)
تمت إضافة:
- Model: `UserDeviceToken`
- Endpoint (JWT): `POST /cad/api/device-token/` لتسجيل token
- Endpoint (JWT): `POST /cad/api/assigned/<cad_number>/reject/` لرفض البلاغ

### إعداد FCM إرسال Push من Django
أضف إلى `settings.py`:
```python
FCM_ENABLED = True
FCM_SERVICE_ACCOUNT_FILE = r"C:\path\to\firebase-service-account.json"
```

ثم ثبّت:
```bash
pip install firebase-admin
python manage.py migrate
```

> بدون `firebase-admin` أو بدون ملف Service Account لن يتم إرسال Push (ولكن النظام لن يتعطل؛ فقط يسجّل تحذير في اللوق).
