# applications/views_review.py
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from finance.models import Payment
from .forms import ApplicationReviewForm
from .models import Application, ApplicationReview


# ---------- Permissions ----------
REVIEW_GROUPS = ["Scholarship Officers", "Reviewer", "Reviewers"]


def can_review(user):
    return user.is_authenticated and user.groups.filter(name__in=REVIEW_GROUPS).exists()


review_required = user_passes_test(can_review)


# ---------- Helpers ----------
def get_payment_summary(application):
    payments = Payment.objects.filter(application=application)
    total_paid = sum((p.amount for p in payments), Decimal("0.00"))

    total_fee = Decimal("0.00")
    if getattr(application, "course", None) and getattr(application.course, "total_tuition_fee", None) is not None:
        total_fee = Decimal(application.course.total_tuition_fee)

    balance = total_fee - total_paid

    if total_fee > 0 and total_paid >= total_fee:
        payment_status = "Fully Paid"
    elif total_paid > 0:
        payment_status = "Partially Paid"
    else:
        payment_status = "Unpaid"

    return {
        "total_fee": total_fee,
        "total_paid": total_paid,
        "balance": balance,
        "payment_status": payment_status,
    }


def get_documents_for_application(application):
    """
    Returns: (template_name, documents_list)
    documents_list is [(label, filefield_or_none), ...]
    """
    if application.is_continuing:
        return (
            "applications/officer_continuing_profile.html",
            [
                ("Academic Transcript", getattr(application, "transcript", None)),
                ("School Fee Structure", getattr(application, "school_fee_structure", None)),
                ("Student ID Card", getattr(application, "id_card", None)),
            ],
        )

    return (
        "applications/officer_new_profile.html",
        [
            ("Grade 12 Certificate", getattr(application, "grade_12_certificate", None)),
            ("Academic Transcript", getattr(application, "transcript", None)),
            ("Acceptance Letter", getattr(application, "acceptance_letter", None)),
            ("School Fee Structure", getattr(application, "school_fee_structure", None)),
            ("Student ID Card", getattr(application, "id_card", None)),
            ("Character Reference 1", getattr(application, "character_reference_1", None)),
            ("Character Reference 2", getattr(application, "character_reference_2", None)),
            ("Statutory Declaration", getattr(application, "statdec", None)),
        ],
    )


def map_review_status_to_application_status(review_status):
    """
    Adjust these mappings to match your status constants.
    """
    mapping = {
        getattr(ApplicationReview, "STATUS_PENDING", "PENDING"): getattr(Application, "STATUS_PENDING", "PENDING"),
        getattr(ApplicationReview, "STATUS_APPROVED", "APPROVED"): getattr(Application, "STATUS_APPROVED", "APPROVED"),
        getattr(ApplicationReview, "STATUS_REJECTED", "REJECTED"): getattr(Application, "STATUS_REJECTED", "REJECTED"),
        getattr(ApplicationReview, "STATUS_NEEDS_INFO", "NEEDS_INFO"): getattr(Application, "STATUS_PENDING", "PENDING"),
    }
    return mapping.get(review_status, getattr(Application, "STATUS_PENDING", "PENDING"))


# ---------- Officer: Review List ----------
@login_required
@review_required
def review_list(request):
    """
    Officer list of applications to review.
    Filter with:
      ?type=new
      ?type=continuing
    """
    app_type = request.GET.get("type")  # "new" | "continuing" | None

    applications = (
        Application.objects.select_related("applicant__user", "institution", "course")
        .order_by("-created_at")
    )

    if app_type == "continuing":
        applications = applications.filter(is_continuing=True)
    elif app_type == "new":
        applications = applications.filter(is_continuing=False)

    return render(
        request,
        "applications/officer_review_list.html",
        {"applications": applications, "app_type": app_type},
    )


# ---------- Officer: Review Detail (New vs Continuing) ----------
@login_required
@review_required
def review_application(request, pk):
    """
    Single officer detail view:
    - auto-selects template based on application.is_continuing
    - shows applicant photo preview
    - shows documents
    - saves timestamped reviews (ApplicationReview) + updates Application.status
    """
    application = get_object_or_404(
        Application.objects.select_related("applicant__user", "institution", "course"),
        pk=pk,
    )

    profile = application.applicant  # ApplicantProfile
    student = profile.user

    # Officer photo preview: prefer per-application face_photo then fallback to profile.photo
    preview_photo = getattr(application, "face_photo", None) or getattr(profile, "photo", None)
    has_profile_photo = bool(preview_photo)

    payment = get_payment_summary(application)
    template_name, documents = get_documents_for_application(application)

    if request.method == "POST":
        form = ApplicationReviewForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                review = form.save(commit=False)
                review.application = application
                review.reviewer = request.user
                review.save()

                application.status = map_review_status_to_application_status(review.status)

                if hasattr(application, "reviewer_note"):
                    application.reviewer_note = review.note

                update_fields = ["status"]
                if hasattr(application, "reviewer_note"):
                    update_fields.append("reviewer_note")
                if hasattr(application, "updated_at"):
                    update_fields.append("updated_at")

                application.save(update_fields=update_fields)

            messages.success(request, "Review saved.")
            return redirect("applications:officer_application_detail", pk=application.pk)

        messages.error(request, "Please correct the errors below.")
    else:
        latest = application.reviews.order_by("-created_at").first()
        form = ApplicationReviewForm(
            initial={
                "status": getattr(latest, "status", getattr(ApplicationReview, "STATUS_PENDING", "PENDING")),
                "note": getattr(latest, "note", "") or getattr(application, "reviewer_note", ""),
            }
        )

    reviews = application.reviews.select_related("reviewer").order_by("-created_at")

    def yn(val):
        return "Yes" if val else "No"

    def safe(getter, fallback="—"):
        v = getter()
        return fallback if v in [None, "", []] else v

    detail_sections = [
        ("Personal Information", [
            ("First Name", safe(lambda: profile.first_name) or safe(lambda: student.first_name)),
            ("Surname", safe(lambda: profile.surname) or safe(lambda: getattr(student, "last_name", ""))),
            ("Gender", safe(lambda: profile.get_gender_display() if hasattr(profile, "get_gender_display") else profile.gender)),
            ("Date of Birth", safe(lambda: profile.date_of_birth)),
            ("Phone Number", safe(lambda: profile.phone_number)),
            ("NID Number", safe(lambda: profile.nid_number)),
            ("Grade 12 Cert No.", safe(lambda: profile.grade12_certificate_number)),
            ("Elementary Completed", yn(profile.elementary_completed)),
            ("Primary Completed", yn(profile.primary_completed)),
            ("Secondary School", safe(lambda: profile.secondary_school_name)),
            ("Year Completed Grade 12", safe(lambda: profile.year_completed_grade12)),
            ("TESAS Category", safe(lambda: profile.tesas_category)),
            ("Active Student ID", safe(lambda: profile.active_student_id)),
        ]),
        ("Residence & Contacts", [
            ("Postal Address", safe(lambda: profile.postal_address)),
            ("Current Residential Area", safe(lambda: profile.current_residential_area)),
            ("Duration Living In", safe(lambda: profile.duration_living_in)),
            ("Current District", safe(lambda: profile.current_district)),
            ("Current LLG", safe(lambda: profile.current_llg)),
        ]),
        ("Origin", [
            ("Origin Province", safe(lambda: profile.origin_province, safe(lambda: getattr(application, "origin_province", None)))),
            ("Origin District", safe(lambda: profile.origin_district, safe(lambda: getattr(application, "origin_district", None)))),
            ("Origin Ward", safe(lambda: profile.origin_ward, safe(lambda: getattr(application, "origin_ward", None)))),
        ]),
        ("Residency", [
            ("Residency Province", safe(lambda: profile.residency_province)),
            ("Residency District", safe(lambda: profile.residency_district)),
            ("Residency Ward", safe(lambda: profile.residency_ward)),
            ("Residency Years", safe(lambda: profile.residency_years)),
        ]),
        ("Father Information", [
            ("Name", safe(lambda: profile.father_name)),
            ("Occupation", safe(lambda: profile.father_occupation)),
            ("Nationality", safe(lambda: profile.father_nationality)),
            ("Province", safe(lambda: profile.father_province)),
            ("District", safe(lambda: profile.father_district)),
            ("LLG", safe(lambda: profile.father_llg)),
            ("Village", safe(lambda: profile.father_village)),
            ("Elementary Completed", yn(profile.father_elementary_completed)),
            ("Primary Completed", yn(profile.father_primary_completed)),
            ("High School Completed", yn(profile.father_highschool_completed)),
        ]),
        ("Mother Information", [
            ("Name", safe(lambda: profile.mother_name)),
            ("Occupation", safe(lambda: profile.mother_occupation)),
            ("Nationality", safe(lambda: profile.mother_nationality)),
            ("Province", safe(lambda: profile.mother_province)),
            ("District", safe(lambda: profile.mother_district)),
            ("LLG", safe(lambda: profile.mother_llg)),
            ("Village", safe(lambda: profile.mother_village)),
            ("Elementary Completed", yn(profile.mother_elementary_completed)),
            ("Elementary Year", safe(lambda: profile.mother_elementary_year)),
            ("Primary Completed", yn(profile.mother_primary_completed)),
            ("Primary Year", safe(lambda: profile.mother_primary_year)),
            ("High School Completed", yn(profile.mother_highschool_completed)),
            ("High School Year", safe(lambda: profile.mother_highschool_year)),
        ]),
    ]

    return render(
        request,
        template_name,
        {
            "application": application,
            "profile": profile,
            "student": student,
            "preview_photo": preview_photo,
            "has_profile_photo": has_profile_photo,
            "documents": documents,
            "payment": payment,
            "form": form,
            "reviews": reviews,
            "detail_sections": detail_sections,
        },
    )
