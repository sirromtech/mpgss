# finance/tasks.py
import logging
from celery import shared_task
from django.db import transaction

from .models import GeneratedPDF
from .pdf_utils import generate_fillable_pdf_for_payment

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_generated_pdf(self, generated_pdf_id):
    """
    Celery task: generate a PDF for a GeneratedPDF row.

    Concurrency-safe:
    - row is locked in a transaction
    - status is set to PROCESSING before leaving transaction
    """
    try:
        with transaction.atomic():
            gen = (
                GeneratedPDF.objects
                .select_for_update()
                .select_related("template", "payment")
                .get(pk=generated_pdf_id)
            )

            if gen.status == "READY":
                return {"status": "already_ready", "id": gen.id}

            # Optional: skip if someone already started it
            if gen.status == "PROCESSING":
                return {"status": "already_processing", "id": gen.id}

            gen.status = "PROCESSING"
            gen.notes = ""
            gen.save(update_fields=["status", "notes"])

        # Generate outside the lock so we don't hold DB transaction while calling external API
        success = generate_fillable_pdf_for_payment(gen.id)

        # pdf_utils should set READY/FAILED + notes. We just re-read final status.
        gen.refresh_from_db(fields=["status", "notes", "file", "external_id"])
        return {"status": gen.status.lower(), "id": gen.id, "success": bool(success)}

    except GeneratedPDF.DoesNotExist:
        logger.warning("GeneratedPDF %s not found", generated_pdf_id)
        return {"status": "missing", "id": generated_pdf_id}

    except Exception as exc:
        logger.exception("Error generating PDF for GeneratedPDF %s", generated_pdf_id)

        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            # best-effort mark failed
            try:
                GeneratedPDF.objects.filter(pk=generated_pdf_id).update(
                    status="FAILED",
                    notes=f"Max retries exceeded: {exc}",
                )
            except Exception:
                pass
            return {"status": "failed_max_retries", "id": generated_pdf_id, "error": str(exc)}
