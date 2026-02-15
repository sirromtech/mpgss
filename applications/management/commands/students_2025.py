import json
from django.core.management.base import BaseCommand
from django.conf import settings
from decimal import Decimal, InvalidOperation

from applications.models import EligibleStudent2025


def clean(value):
    if value is None:
        return ""
    return str(value).strip()


def to_decimal(value):
    value = clean(value)
    if not value:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


class Command(BaseCommand):
    help = "Import 2025 students from JSON into EligibleStudent2025 table"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing records before import"
        )

    def handle(self, *args, **options):
        json_path = settings.STUDENTS_2025_JSON_PATH

        if not json_path.exists():
            self.stdout.write(self.style.ERROR(f"JSON file not found: {json_path}"))
            return

        if options["clear"]:
            EligibleStudent2025.objects.all().delete()
            self.stdout.write(self.style.WARNING("Existing records deleted."))

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict) and "rows" in data:
            data = data["rows"]

        if not isinstance(data, list):
            self.stdout.write(self.style.ERROR("JSON must contain a list of students."))
            return

        created = 0
        batch = []

        for record in data:
            first_name = clean(record.get("First Name") or record.get("First Name "))
            surname = clean(record.get("Surname"))

            if not first_name or not surname:
                continue

            batch.append(
                EligibleStudent2025(
                    first_name=first_name,
                    surname=surname,
                    gender=clean(record.get("Gender")),
                    institution=clean(record.get("Institution")),
                    course=clean(record.get("Course") or record.get("Course ")),
                    tuition_fee=to_decimal(record.get("Tuition Fee")),
                    district=clean(record.get("District")),
                    year_of_study=clean(record.get("Year Of Study")),
                )
            )

            if len(batch) >= 1000:
                EligibleStudent2025.objects.bulk_create(batch, batch_size=1000)
                created += len(batch)
                batch = []

        if batch:
            EligibleStudent2025.objects.bulk_create(batch, batch_size=1000)
            created += len(batch)

        self.stdout.write(self.style.SUCCESS(f"Successfully imported {created} students."))
