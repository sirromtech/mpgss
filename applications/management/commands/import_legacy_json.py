# applications/management/commands/import_legacy_json.py
import json
from decimal import Decimal
from django.core.management.base import BaseCommand
from applications.models import LegacyStudent
from django.conf import settings

class Command(BaseCommand):
    help = "Import legacy students from JSON file with normalization"

    def handle(self, *args, **kwargs):
        path = settings.BASE_DIR / "data" / "legacy_students.json"
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        for record in raw:
            first_name = record.get("First Name ", "").strip()
            surname = record.get("Surname", "").strip()
            institution = record.get("Institution", "").strip()
            course = record.get("Course ", "").strip()
            year_str = record.get("Year Of Study", "").strip()
            year = None
            if year_str.lower().startswith("year"):
                try:
                    year = int(year_str.replace("Year", "").strip())
                except ValueError:
                    year = None
            tuition = Decimal(record.get("Tuition Fee", "0").strip())

            LegacyStudent.objects.update_or_create(
                first_name=first_name,
                surname=surname,
                defaults={
                    "institution": institution,
                    "course": course,
                    "year_of_study": year,
                    "tuition_fee": tuition,
                }
            )

        self.stdout.write(self.style.SUCCESS("Legacy students imported successfully"))
