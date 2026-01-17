# applications/tasks.py
from celery import shared_task
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.urls import reverse
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_application_status_email(self, review_id):
    """
    Send an email to the applicant when an ApplicationReview is created or its status changes.
    """
    from .models import ApplicationReview  # local import avoids startup circulars

    try:
        review = (
            ApplicationReview.objects
            .select_related("application__applicant__user", "reviewer", "application__institution", "application__course")
            .get(pk=review_id)
        )

        user = review.application.applicant.user
        to_email = (user.email or "").strip()
        if not to_email:
            logger.warning("No email for user=%s (review=%s). Skipping notification.", user.pk, review.pk)
            return

        applicant_name = user.get_full_name().strip() or user.username
        application = review.application

        # Build application URL (use correct view name)
        base = getattr(settings, "SITE_URL", "").rstrip("/")
        app_url = ""
        try:
            path = reverse("applications:user_dashboard")
            app_url = f"{base}{path}" if base else path

        except Exception:
            app_url = f"{base}/applications/{application.pk}/" if base else f"/applications/{application.pk}/"

        context = {
            "applicant_name": applicant_name,
            "user": user,
            "application": application,
            "review": review,
            "app_url": app_url,
        }

        subject = render_to_string("emails/application_status_subject.txt", context).strip()
        if not subject:
            subject = f"Update on your application #{application.pk}"

        # Render bodies
        text_body = render_to_string("emails/application_status_notification.txt", context)
        html_body = render_to_string("emails/application_status_notification.html", context)

        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or "no-reply@example.com"

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_body,              # ✅ keep plain text as-is
            from_email=from_email,
            to=[to_email],
        )
        if html_body and html_body.strip():
            email.attach_alternative(html_body, "text/html")

        email.send(fail_silently=False)
        logger.info("Sent application status email for review %s to %s", review.pk, to_email)

    except ApplicationReview.DoesNotExist:
        logger.warning("ApplicationReview %s does not exist, skipping email", review_id)

    except Exception as exc:
        logger.exception("Failed to send application status email for review %s", review_id)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("Max retries exceeded for sending application status email for review %s", review_id)
