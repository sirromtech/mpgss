import logging
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import ApplicationReview
from .tasks import send_application_status_email, send_status_update_email

logger = logging.getLogger(__name__)

@receiver(pre_save, sender=ApplicationReview)
def cache_old_review_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._old_status = sender.objects.only("status").get(pk=instance.pk).status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None

@receiver(post_save, sender=ApplicationReview)
def notify_applicant_on_review(sender, instance, created, **kwargs):
    """
    Email applicant when review is created OR status changes.
    """
    try:
        old_status = getattr(instance, "_old_status", None)
        new_status = instance.status

        status_changed = created or (old_status != new_status)
        if not status_changed:
            return

        transaction.on_commit(lambda: send_application_status_email.delay(instance.pk))
        logger.info("Queued status email for review %s (old: %s, new: %s)", instance.pk, old_status, new_status)

    except Exception:
        logger.exception("Failed to enqueue application status email for review %s", getattr(instance, "pk", None))
