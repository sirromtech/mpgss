from django.core.management.base import BaseCommand
from django.utils import timezone
from applications.models import ApplicationConfig, ApplicantProfile

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        cfg = ApplicationConfig.get_solo()
        if not cfg.rollover_due():
            self.stdout.write("Rollover not due.")
            return

        # Add a boolean field if you want (recommended):
        # ApplicantProfile.is_continuing_applicant = models.BooleanField(default=False)

        updated = ApplicantProfile.objects.all().update(is_continuing_applicant=True)

        cfg.legacy_lookup_enabled = False
        cfg.save(update_fields=["legacy_lookup_enabled"])
        self.stdout.write(self.style.SUCCESS(f"Rollover completed. Updated {updated} profiles."))
