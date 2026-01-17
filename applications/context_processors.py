# applications/context_processors.py
from .models import ApplicantProfile, Application

OFFICER_GROUP = "Scholarship Officers"

def user_context(request):
    user = request.user

    context = {
        "has_application": False,
        "is_student": False,
        "is_officer": False,
        "is_admin": False,
    }

    if not user.is_authenticated:
        return context

    # Admin should win
    if user.is_superuser:
        context["is_admin"] = True
        return context

    # Officer
    if user.groups.filter(name='Scholarship Officers').exists():
        context["is_officer"] = True
        return context

    # Student
    profile = ApplicantProfile.objects.filter(user=user).only("id").first()
    if profile:
        context["is_student"] = True
        context["has_application"] = Application.objects.filter(applicant_id=profile.id).exists()

    return context

def application_status(request):
    """
    Custom context processor that adds application status info
    to all templates.
    """
    return {
        'application_status': 'open',  # or dynamic value
    }
