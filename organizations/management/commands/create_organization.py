from django.core.management.base import BaseCommand
from organizations.models import Organization


class Command(BaseCommand):
    help = "إنشاء جهة جديدة مع توليد كود تلقائي 5 أرقام"

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help="اسم الجهة")

    def handle(self, *args, **options):
        name = options["name"].strip()

        if Organization.objects.filter(name=name).exists():
            self.stdout.write(self.style.ERROR("الجهة موجودة مسبقًا."))
            return

        org = Organization.objects.create(name=name)

        self.stdout.write(
            self.style.SUCCESS(
                f"تم إنشاء الجهة بنجاح:\n"
                f"الاسم: {org.name}\n"
                f"الكود: {org.code}"
            )
        )
