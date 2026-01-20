from celery import shared_task
from .utils import trigger_swiftmassive_event
from django.contrib.auth import get_user_model
from django.conf import settings
from django.urls import reverse

User = get_user_model()

@shared_task(bind=True, max_retries=3)
def send_application_status_email(self, review_id):
    from .models import ApplicationReview
    try:
        review = ApplicationReview.objects.select_related("application__applicant__user").get(pk=review_id)
        user = review.application.applicant.user
        
        trigger_swiftmassive_event(
            email=user.email,
            event_name="application_status_update",
            data_dict={
                "first_name": user.first_name or user.username,
                "current_status": review.status,
                "login_url": f"{settings.SITE_URL}/dashboard/"
            }
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_welcome_email_task(self, user_id):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
        
        # 1. Get the base domain from Render settings
        # Ensure SITE_URL is "https://mpgss-ycle.onrender.com" in Render Env Vars
        base = getattr(settings, "SITE_URL", "https://mpgss-ycle.onrender.com").rstrip("/")
        
        # 2. Get the path for 'login' from your urls.py
        login_path = reverse("login") # This returns "/login/"
        
        # 3. Combine them into a single string to send to Swiftmassive
        full_login_url = f"{base}{login_path}"
        
        trigger_swiftmassive_event(
            email=user.email,
            event_name="welcome_email",
            data={
                "first_name": user.first_name or user.username,
                "login_url": full_login_url  # This is the string Swiftmassive will use in the href
            }
        )
    except Exception as exc:
        raise self.retry(exc=exc)