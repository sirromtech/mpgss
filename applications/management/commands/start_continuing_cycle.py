# applications/management/commands/start_continuing_cycle.py
from datetime import timedelta
import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from applications.models import Application

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Create continuing student applications for eligible approved applications.\n\n"
        "Defaults:\n"
        " - Finds applications with status APPROVED submitted at least N days ago\n"
        " - Creates a new continuing Application for the next year if one does not exist\n\n"
        "Options:\n"
        "  --days N       Consider applications older than N days (default 365)\n"
        "  --dry-run      Do not create records; only print what would be done\n"
        "  --limit N      Stop after processing N applications (0 = no limit)\n"
        "  --force        Force creation even if checks fail (use carefully)\n"
    )

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=365)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]
        limit = options["limit"]
        force = options["force"]

        now = timezone.now()
        cutoff = now - timedelta(days=days)

        self.stdout.write(f"Starting continuing-cycle run at {now.isoformat()}")
        self.stdout.write(f"Looking for APPROVED applications submitted on/before {cutoff.date()} (days={days})")
        if dry_run:
            self.stdout.write("DRY RUN mode: no database changes will be made.")
        if force:
            self.stdout.write("FORCE mode: checks may be bypassed.")

        qs = (
            Application.objects
            .select_related("course", "applicant")
            .filter(status=Application.STATUS_APPROVED, submission_date__lte=cutoff)
            .order_by("submission_date")
        )

        processed = created_count = skipped_count = errors = 0

        for app in qs.iterator():
            if limit and processed >= limit:
                break
            processed += 1

            try:
                self.stdout.write(
                    f"\n[{processed}] App id={app.id} applicant={getattr(app.applicant, 'id', 'N/A')} "
                    f"course={getattr(app.course, 'id', 'N/A')} year={app.year_of_study}"
                )

                # Must have course + year_of_study unless force
                if (not app.course or not app.year_of_study) and not force:
                    self.stdout.write("  SKIP: Missing course or year_of_study")
                    skipped_count += 1
                    continue

                max_years = getattr(app.course, "years_of_study", None) if app.course else None
                if max_years and app.year_of_study and app.year_of_study >= max_years:
                    if app.status not in (Application.STATUS_GRADUATING, Application.STATUS_PASSOUT):
                        if dry_run:
                            self.stdout.write(f"  WOULD MARK GRADUATING (year {app.year_of_study} >= {max_years})")
                        else:
                            app.status = Application.STATUS_GRADUATING
                            app.save(update_fields=["status", "updated_at"])
                            self.stdout.write("  MARKED GRADUATING")
                    else:
                        self.stdout.write("  Already graduating/passout; no continuation.")
                    skipped_count += 1
                    continue

                next_year = (app.year_of_study or 0) + 1
                existing = Application.objects.filter(
                    original_application=app,
                    is_continuing=True,
                    year_of_study=next_year
                ).only("id").first()

                if existing:
                    self.stdout.write(f"  SKIP: continuation exists for year {next_year} (id={existing.id})")
                    skipped_count += 1
                    continue

                # Eligibility check (bypass if force)
                if not force and not app.can_start_continuing_cycle():
                    self.stdout.write("  SKIP: can_start_continuing_cycle() returned False")
                    skipped_count += 1
                    continue

                if dry_run:
                    self.stdout.write(f"  WOULD CREATE continuing application for next_year={next_year}")
                    created_count += 1
                    continue

                with transaction.atomic():
                    if force:
                        # Force-create even if model helper blocks
                        cont = Application.objects.create(
                            applicant=app.applicant,
                            institution=app.institution,
                            course=app.course,
                            original_application=app,
                            is_continuing=True,
                            year_of_study=next_year,
                            status=Application.STATUS_PENDING,
                            last_cycle_started_at=now,
                        )
                        app.last_cycle_started_at = now
                        app.save(update_fields=["last_cycle_started_at"])
                    else:
                        cont = app.create_continuing_application(when=now)

                if cont:
                    created_count += 1
                    self.stdout.write(f"  CREATED continuation id={cont.id} year={cont.year_of_study}")
                else:
                    self.stdout.write("  SKIP: create_continuing_application returned None")
                    skipped_count += 1

            except Exception as exc:
                errors += 1
                logger.exception("Error processing application id=%s", getattr(app, "id", "N/A"))
                self.stderr.write(f"  ERROR processing app id={getattr(app, 'id', 'N/A')}: {exc}")

        self.stdout.write("\nRun complete.")
        self.stdout.write(f"Processed: {processed}")
        self.stdout.write(f"Created (or would create in dry-run): {created_count}")
        self.stdout.write(f"Skipped: {skipped_count}")
        self.stdout.write(f"Errors: {errors}")

        if errors:
            raise CommandError(f"Completed with {errors} error(s). Check logs for details.")
