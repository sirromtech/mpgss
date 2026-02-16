# applications/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from .models import ApplicantProfile, Application, ApplicationConfig
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.db.models import Q, Count, Sum, F
from django.contrib.admin.views.decorators import staff_member_required
from utils.ai_scanner import scan_documents_for_eligibility
from institutions.models import Institution, Course
from finance.models import Payment # assuming this exists
from finance.views import finance_summary_totals 
from django.dispatch import receiver
from allauth.account.signals import user_logged_in
from django.core.mail import send_mail
from django.urls import reverse
from django.contrib.auth.forms import SetPasswordForm
from utils.decorators import require_password_setup
from django.core.paginator import Paginator
from django.conf import settings
from .models import FAQ, PolicyPage
from utils.progress import set_progress, get_progress, clear_progress
import uuid
import threading
from .forms import ApplicationForm, ApplicantProfileForm
from django.http import JsonResponse
import time
from django.utils import timezone
from django.db.models.functions import Coalesce
import csv
from django.http import HttpResponse
from decimal import Decimal, ROUND_HALF_UP
from .forms import ContinuingProfileForm, ContinuingApplicationForm 
from .forms import LegacyLookupForm
from django.views.decorators.http import require_http_methods
from .models import LegacyStudent
import re
import logging
from django.urls import reverse_lazy
from django.views.generic.edit import UpdateView
from django.utils.http import url_has_allowed_host_and_scheme
from django.db import transaction
from .models import ApplicationConfig
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
import requests
from .forms import SignupForm
from .utils import trigger_swiftmassive_event

logger = logging.getLogger(__name__)


OFFICER_GROUPS = ["Scholarship Officers", "Reviewer", "Reviewers"]

def dashboard_redirect(request):
    user = request.user

    # Officers → officer dashboard
    if user.groups.filter(name__in=OFFICER_GROUPS).exists():
        return redirect("applications:officer_dashboard")

    # Admin/staff → admin
    if user.is_staff or user.is_superuser:
        return redirect(reverse("admin:index"))

    # Students
    profile = ApplicantProfile.objects.filter(user=user).first()

    # No profile yet → go to apply choice (New vs Continuing)
    if not profile:
        return redirect("applications:apply")

    # Has at least one application → go to dashboard
    if Application.objects.filter(applicant=profile).exists():
        return redirect("applications:user_dashboard")

    # Profile exists but no application yet → go to apply choice
    return redirect("applications:apply")


def login_view(request):
    from .forms import UserLoginForm

    if request.user.is_authenticated:
        return dashboard_redirect(request)

    if request.method == "POST":
        form = UserLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")
            return dashboard_redirect(request)

        messages.error(request, "Invalid username or password.")
    else:
        form = UserLoginForm()

    return render(request, "applications/login.html", {"form": form})




def logout_view(request):
    if request.method == "POST" or request.method == "GET":
        logout(request)
        messages.success(request, "You have been logged out.")
        return redirect("applications:login")
# --- Home ---

def home_view(request):
    total_applicants = Application.objects.count()
    total_awarded = Application.objects.filter(status=Application.STATUS_APPROVED).count()

    institution_stats = (
        Application.objects
        .values('institution__name')
        .annotate(
            applicants=Count('id'),
            awarded=Count('id', filter=Q(status=Application.STATUS_APPROVED))
        )
        .order_by('-applicants')
    )

    logos = range(1, 26)  # ✅ Restore logo numbers (1.png → 25.png)

    return render(request, 'home.html', {
        'total_applicants': total_applicants,
        'total_awarded': total_awarded,
        'institution_stats': institution_stats,
        'logos': logos,  # ✅ Pass to template
    })


# --- Officer check ---

def is_scholarship_officer(user):
    return user.is_authenticated and user.groups.filter(name='Scholarship Officers').exists()

@user_passes_test(is_scholarship_officer)
def officer_view_student_profile(request, pk):
    student = get_object_or_404(ApplicantProfile, pk=pk)
    return render(request, 'applications/officer_student_profile.html', {'student': student})

# --- Authentication ---
def signup_view(request):
    from .forms import SignupForm
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Account created successfully. Please log in.")
            return redirect('applications:login')
        else:
            messages.error(request, "Signup failed. Please correct the errors below.")
    else:
        form = SignupForm()
    return render(request, 'applications/signup.html', {'crispy_form': form})

def send_swiftmissive_event(event_name, email, variables=None):
    """
    Trigger a SwiftMissive event with optional variables.
    """
    url = "https://ghz0jve3kj.execute-api.us-east-1.amazonaws.com/events"

    event = {
        "name": event_name,
        "email": email,
    }
    if variables:
        event.update(variables)

    payload = {"events": [event]}
    headers = {
        "x-api-key": settings.SWIFTMISSIVE_API_KEY,
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)

    # Debug logging
    print("=== SwiftMissive Debug ===")
    print("Payload:", payload)
    print("Response Code:", response.status_code)
    print("Response Body:", response.text)
    print("==========================")

    return response.status_code, response.text





def register(request):
    """
    Handles user registration:
    - Validates Cloudflare Turnstile
    - Creates inactive user
    - Generates email verification link
    - Sends SwiftMissive 'Welcome_email' event
    - Redirects to login until verified
    """
    if request.method == "POST":
        form = SignupForm(request.POST)
        token = request.POST.get("cf-turnstile-response")
        secret_key = settings.CLOUDFLARE_TURNSTILE_SECRET_KEY

        verify_url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
        data = {
            "secret": secret_key,
            "response": token,
            "remoteip": request.META.get("REMOTE_ADDR"),
        }
        result = requests.post(verify_url, data=data).json()

        if result.get("success") and form.is_valid():
            user = form.save(commit=False)
            user.is_active = False  # require email verification
            user.save()

            # Generate verification link

    return render(request, "signup.html", {
        "form": form,
        "CLOUDFLARE_TURNSTILE_SITE_KEY": settings.CLOUDFLARE_TURNSTILE_SITE_KEY,
    })



@require_http_methods(["GET", "POST"])
def confirm_legacy(request, no: int):
    legacy = find_legacy_by_no(no)
    if not legacy:
        messages.error(request, "No legacy record found.")
        return redirect("applications:lookup_legacy")

    # Get the current applicant’s continuing application
    profile = request.user.applicantprofile
    application = get_object_or_404(Application, applicant=profile, is_continuing=True)

    # Map legacy record to institution/course
    matched_institution = Institution.objects.filter(name__iexact=legacy.get("institution")).first()
    matched_course = Course.objects.filter(name__iexact=legacy.get("course")).first()

    # ✅ Set institution and course once, not editable later
    if matched_institution:
        application.institution = matched_institution
    if matched_course:
        application.course = matched_course
    application.save(update_fields=["institution", "course"])

    if request.method == "POST":
        # Persist claim (session or DB)
        request.session["claimed_legacy_no"] = legacy.get("no")
        messages.success(request, "Legacy record confirmed. Please upload your documents.")
        return redirect("applications:upload_documents")  # adjust to your next step

    return render(request, "applications/confirm_legacy.html", {
        "legacy": legacy,
        "application": application,
    })


class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']

class UserLoginForm(AuthenticationForm):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)


@login_required
def create_application(request):
    cfg = ApplicationConfig.get_solo()
    if cfg.is_closed_now():
        return applications_closed_response(request)

    profile, created = ApplicantProfile.objects.get_or_create(user=request.user)

    if Application.objects.filter(applicant=profile, is_continuing=False).exists():
        messages.info(request, "You have already submitted a new student application.")
        return redirect("applications:user_dashboard")

    if request.method == "POST":
        app_form = ApplicationForm(request.POST, request.FILES)
        profile_form = ApplicantProfileForm(request.POST, instance=profile)

        if app_form.is_valid() and profile_form.is_valid():
            profile_form.save()

            application = app_form.save(commit=False)
            application.applicant = profile
            application.is_continuing = False
            application.save()

            # ---- SIMPLE SYNCHRONOUS SCAN ----
            try:
                scan_result = scan_documents_for_eligibility(application)
                application.reviewer_note = scan_result
            except Exception as exc:
                application.reviewer_note = f"Scan failed: {exc}"

            application.save(update_fields=["reviewer_note"])
            # --------------------------------

            return redirect("applications:documents_submitted")

    else:
        app_form = ApplicationForm()
        profile_form = ApplicantProfileForm(instance=profile)

    return render(request, "applications/application_form.html", {
        "app_form": app_form,
        "profile_form": profile_form,
        "profile": profile,
    })

@login_required
def documents_submitted(request):
    return render(request, "applications/documents_submitted.html")


@login_required
def choose_application_type(request):
    profile, _ = ApplicantProfile.objects.get_or_create(user=request.user)

    return render(request, "applications/choose_application_type.html", {
        "profile": profile,
    })

@login_required
def create_continuing_application(request):
    cfg = ApplicationConfig.get_solo()
    if cfg.is_closed_now():
        return applications_closed_response(request)

    profile_id = request.session.get('continuing_profile_id')
    if not profile_id:
        messages.error(request, "Please verify your identity first.")
        return redirect('applications:lookup')

    profile = ApplicantProfile.objects.get(id=profile_id)

    if request.method == 'POST':
        form = ContinuingApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            application = form.save(commit=False)
            application.applicant = profile
            application.is_continuing = True
            application.save()
            

            messages.success(request, "Continuing student application submitted successfully.")
            return redirect('applications:application_success')
    else:
        form = ContinuingApplicationForm()

    return render(request, 'applications/continuing_application_form.html', {
        'form': form,
        'profile': profile,
    })

@login_required
def application_success(request):
    return redirect('applications:dashboard')

# --- Officer ---
def is_scholarship_officer(user):
    return user.is_authenticated and user.groups.filter(name='Scholarship Officers').exists()

# adjust these imports to match your project
from .models import Application, Institution
try:
    from finance.models import Payment, BudgetVote
    PAYMENT_AVAILABLE = True
except Exception:
    PAYMENT_AVAILABLE = False
    Payment = None
    BudgetVote = None

def is_scholarship_officer(user):
    # keep your existing check here
    return user.is_active and user.groups.filter(name='Scholarship Officers').exists()

@user_passes_test(is_scholarship_officer)
def officer_dashboard(request):
    """
    Officer dashboard showing:
      - searchable, paginated applications list
      - aggregated institution-level stats (counts by status)
      - top 5 preview applications
      - optional financial totals for approved pool if Payment model exists
    """
    query = request.GET.get('q', '').strip()
    page = int(request.GET.get('page', 1))

    # Base queryset for listing/search
    applications_qs = Application.objects.select_related('applicant__user', 'institution', 'course')

    if query:
        applications_qs = applications_qs.filter(
            Q(applicant__user__first_name__icontains=query) |
            Q(applicant__user__last_name__icontains=query) |
            Q(institution__name__icontains=query) |
            Q(applicant__user__email__icontains=query)
        )

    applications_qs = applications_qs.order_by('-submission_date')

    # Paginate the full list (for the "applications" view)
    paginator = Paginator(applications_qs, 25)
    applications_page = paginator.get_page(page)

    # Institution-level aggregated stats in a single query (avoids looping)
    institution_stats_qs = (
        Application.objects
        .values('institution__id', 'institution__name')
        .annotate(
            total=Count('id'),
            approved=Count('id', filter=Q(status=Application.STATUS_APPROVED)),
            rejected=Count('id', filter=Q(status=Application.STATUS_REJECTED)),
            pending=Count('id', filter=Q(status=Application.STATUS_PENDING)),
        )
        .order_by('institution__name')
    )

    # Convert to list of dicts including id so templates can reverse URLs
    institution_stats = [
        {
            'id': item['institution__id'],
            'name': item['institution__name'],
            'total': item['total'],
            'approved': item['approved'],
            'rejected': item['rejected'],
            'pending': item['pending'],
        }
        for item in institution_stats_qs
    ]

    # Overall totals (single-query counts)
    totals = Application.objects.aggregate(
        total_applications=Count('id'),
        total_approved=Count('id', filter=Q(status=Application.STATUS_APPROVED)),
        total_rejected=Count('id', filter=Q(status=Application.STATUS_REJECTED)),
        total_pending=Count('id', filter=Q(status=Application.STATUS_PENDING)),
    )

    # Preview: top 5 recent applications (already ordered)
    preview_applications = applications_qs[:5]

    # Optional: compute financial aggregates for approved pool (global)
    finance_totals = None
    committed_total = paid_total = remaining_total = Decimal('0.00')
    paid_percent = 0
    payments = []
    budget_votes = []
    if PAYMENT_AVAILABLE:
        approved_qs = Application.objects.filter(status=Application.STATUS_APPROVED)
        finance_totals = approved_qs.aggregate(
            pool_total_tuition=Coalesce(Sum('course__total_tuition_fee'), Decimal('0.00')),
            pool_total_paid=Coalesce(Sum('payments__amount', filter=Q(payments__status=Payment.STATUS_PAID)), Decimal('0.00')),
            pool_total_committed=Coalesce(Sum('payments__amount', filter=Q(payments__status=Payment.STATUS_COMMITTED)), Decimal('0.00')),
        )
        finance_totals['pool_total_outstanding'] = finance_totals['pool_total_tuition'] - finance_totals['pool_total_paid']

        # convenience totals for the top widgets
        committed_total = finance_totals.get('pool_total_committed', Decimal('0.00')) or Decimal('0.00')
        paid_total = finance_totals.get('pool_total_paid', Decimal('0.00')) or Decimal('0.00')
        remaining_total = committed_total - paid_total
        try:
            paid_percent = int((paid_total / committed_total * 100).quantize(Decimal('1'))) if committed_total and committed_total != Decimal('0.00') else 0
        except Exception:
            paid_percent = 0

        # recent payments for the finance table (limit to 25)
        payments = Payment.objects.select_related('application__institution', 'application').order_by('-payment_date')[:25]

        # budget votes if model exists
        if BudgetVote is not None:
            budget_votes = BudgetVote.objects.all().order_by('vote_code')

    # Additional context used by templates
    institutions_list = Institution.objects.order_by('name').all()
    statuses = {
        '': 'All',
        'APPROVED': 'Approved',
        'PENDING': 'Pending',
        'REJECTED': 'Rejected',
        'COMMITTED': 'Committed',
        'PAID': 'Paid',
        'CANCELLED': 'Cancelled',
        'NEEDS_INFO': 'Needs info',
    }

    # other stats for right column
    applications_for_stats = applications_qs  # or Application.objects.all() if you want global counts
    total_awarded = Application.objects.filter(status=Application.STATUS_APPROVED).count()

    institutions_count = Institution.objects.count()

    context = {
        'applications_page': applications_page,            # paginated full list
        'applications': applications_for_stats,           # queryset used for counts in template
        'preview_applications': preview_applications,      # top 5 preview
        'institution_stats': institution_stats,           # list of dicts with id & name
        'institutions_list': institutions_list,           # for filter select
        'statuses': statuses,                             # for filter select
        'totals': totals,
        'finance_totals': finance_totals,                  # None if Payment not available
        'committed_total': committed_total,
        'paid_total': paid_total,
        'remaining_total': remaining_total,
        'paid_percent': paid_percent,
        'payments': payments,
        'budget_votes': budget_votes,
        'query': query,
        'allow_export': True,                              # toggle as needed
        'total_awarded': total_awarded,
        'institutions_count': institutions_count,
    }
    
    context.update(finance_summary_totals())
    
    return render(request, 'applications/officer_dashboard.html', context)


def format_currency(amount):
    # amount is Decimal or numeric
    amt = Decimal(amount or 0).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return f"PGK{amt:,.2f}"

def export_applications_csv(request):
    """
    Export applications grouped by institution with per-institution subtotal and grand total.
    Accepts GET filters: q (search), status, institution_id (optional).
    """
    q = request.GET.get('q', '').strip()
    status = (request.GET.get("status") or "").strip().upper()

    # Force status selection so it won't export everything by accident
    if not status:
        return HttpResponse("Please select a status to export (APPROVED / REJECTED / PENDING).", status=400)

    allowed_statuses = {"APPROVED", "REJECTED", "PENDING"}
    if status not in allowed_statuses:
        return HttpResponse(f"Invalid status '{status}'. Use APPROVED / REJECTED / PENDING.", status=400)

    qs = qs.filter(status=status)

    if institution_id:
        qs = qs.filter(institution_id=institution_id)

    # Group by institution in Python to write subtotals in order
    # Build a mapping: institution -> list of applications
    apps_by_inst = {}
    inst_order = []
    for app in qs:
        inst = app.institution.name if app.institution else 'Unknown'
        if inst not in apps_by_inst:
            apps_by_inst[inst] = []
            inst_order.append(inst)
        apps_by_inst[inst].append(app)

    # Prepare response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="applications_export.csv"'

    writer = csv.writer(response)

    # Header block (match image top lines)
    writer.writerow(['MOROBE PROVINCIAL GOVERNMENT'])
    writer.writerow(['GERSON SOLULU SCHOLARSHIP PROGRAM 2026'])
    writer.writerow([])  # blank line
    writer.writerow(['No.', 'First Name', 'Surname', 'Gender', 'Institution', 'Course', 'Tuition Fee', 'District', 'Year Of Study'])

    grand_total = Decimal('0.00')

    # Write rows grouped by institution
    for inst_name in inst_order:
        apps = apps_by_inst[inst_name]
        # Institution title row
        writer.writerow([])
        writer.writerow([inst_name])  # institution header row

        inst_subtotal = Decimal('0.00')
        for idx, app in enumerate(apps, start=1):
            tuition = getattr(app.course, 'total_tuition_fee', None) or Decimal('0.00')
            inst_subtotal += Decimal(tuition)
            writer.writerow([
                idx,
                app.applicant.user.first_name if app.applicant and app.applicant.user else '',
                app.applicant.user.last_name if app.applicant and app.applicant.user else '',
                app.applicant.gender if hasattr(app.applicant.user, 'profile') and getattr(app.applicant.user.profile, 'gender', None) else getattr(app, 'gender', ''),
                inst_name,
                app.course.name if app.course else '',
                format_currency(tuition),
                getattr(app, 'district', '') or '',
                getattr(app, 'year_of_study', '') or '',
            ])

        # Institution subtotal row
        writer.writerow([])
        writer.writerow(['', '', '', '', '', 'Institution total', format_currency(inst_subtotal)])
        grand_total += inst_subtotal

    # Grand total at the end
    writer.writerow([])
    writer.writerow(['', '', '', '', '', 'Grand total', format_currency(grand_total)])

    return response



def is_scholarship_officer(user):
    return user.is_active and user.groups.filter(name="Scholarship Officers").exists()

def is_scholarship_officer(user):
    return user.is_authenticated and user.groups.filter(name="Scholarship Officers").exists()

@user_passes_test(is_scholarship_officer)
def officer_view_student_profile(request, pk):
    # pk here is ApplicantProfile.pk (NOT Application.pk)
    student = get_object_or_404(
        ApplicantProfile.objects.select_related("user"),
        pk=pk
    )

    applications = (
        Application.objects
        .filter(applicant=student)
        .select_related("institution", "course")
        .order_by("-created_at")
    )

    return render(request, "applications/officer_student_profile.html", {
        "student": student,
        "applications": applications,
    })


# --AI Scan ---
@staff_member_required
def review_application(request, pk):
    application = get_object_or_404(Application, pk=pk)

    if request.method == 'POST':
        status = request.POST.get('status')
        note = request.POST.get('reviewer_note')
        application.status = status
        application.reviewer_note = note
        application.save()
        
        

        messages.success(request, "Application updated successfully.")
        return redirect('applications:officer_dashboard')

    return render(request, 'applications/review_application.html', {'application': application})


@require_password_setup
@login_required
def user_dashboard(request):
    profile = ApplicantProfile.objects.filter(user=request.user).first()
    if not profile:
        return redirect('applications:create_application')

    applications = Application.objects.filter(applicant=profile).select_related('institution', 'course')

    enriched_apps = []
    for app in applications:
        # ✅ single upload field for all applications (new + continuing)
        documents = [
            ('Uploaded Documents (PDF)', getattr(app, "documents_pdf", None)),
        ]

        total_paid = Payment.objects.filter(
            application=app,
            status=Payment.STATUS_PAID
        ).aggregate(total=Coalesce(Sum('amount'), Decimal('0.00')))['total']

        total_fee = getattr(app.course, 'total_tuition_fee', Decimal('0.00')) or Decimal('0.00')
        balance = Decimal(total_fee) - Decimal(total_paid)
        if balance < 0:
            balance = Decimal('0.00')

        payment_status = (
            'Fully Paid' if total_paid >= total_fee else
            'Partially Paid' if total_paid > 0 else
            'Unpaid'
        )

        enriched_apps.append({
            'app': app,
            'documents': documents,
            'total_paid': total_paid,
            'balance': balance,
            'payment_status': payment_status
        })

    # If all apps are continuing, use continuing dashboard
    if all(item['app'].is_continuing for item in enriched_apps):
        return render(request, 'applications/continuing_dashboard.html', {
            'applications': enriched_apps,
            'profile': profile,
        })

    # Otherwise use default dashboard
    return render(request, 'applications/applicant_dashboard.html', {
        'applications': enriched_apps,
        'profile': profile,
    })


@login_required
def continuing_dashboard(request):
    profile = ApplicantProfile.objects.filter(user=request.user).first()
    if not profile:
        return redirect('applications:create_application')

    applications = Application.objects.filter(applicant=profile, is_continuing=True).select_related('institution', 'course')

    enriched_apps = []
    for app in applications:
        # ✅ single upload field
        documents = [
            ('Uploaded Documents (PDF)', getattr(app, "documents_pdf", None)),
        ]

        total_paid = Payment.objects.filter(
            application=app,
            status=Payment.STATUS_PAID
        ).aggregate(total=Coalesce(Sum('amount'), Decimal('0.00')))['total']

        total_fee = getattr(app.course, 'total_tuition_fee', Decimal('0.00')) or Decimal('0.00')
        balance = Decimal(total_fee) - Decimal(total_paid)
        if balance < 0:
            balance = Decimal('0.00')

        payment_status = (
            'Fully Paid' if total_paid >= total_fee else
            'Partially Paid' if total_paid > 0 else
            'Unpaid'
        )

        enriched_apps.append({
            'app': app,
            'documents': documents,
            'total_paid': total_paid,
            'balance': balance,
            'payment_status': payment_status
        })

    return render(request, 'applications/continuing_dashboard.html', {
        'applications': enriched_apps,
        'profile': profile,
    })


@login_required
@user_passes_test(lambda u: u.groups.filter(name__in=["Reviewer", "Scholarship Officers"]).exists())
def view_review(request, pk):
    application = get_object_or_404(
        Application.objects.select_related("applicant__user", "institution", "course"),
        pk=pk
    )

    reviews = application.reviews.select_related("reviewer").order_by("-created_at")

    # ✅ Single document for BOTH new and continuing
    documents = {
        "Uploaded Documents (PDF)": application.documents_pdf
    }

    # You can still keep different templates if you want
    template = (
        "officer/review_continuing.html"
        if application.is_continuing
        else "officer/review_new.html"
    )

    return render(request, template, {
        "application": application,
        "applicant": application.applicant,
        "documents": documents,
        "reviews": reviews,
        "review_form": ApplicationReviewForm(),
    })


try:
    from .models import News
except Exception:
    News = None

def news_list(request):
    if News is not None:
        qs = News.objects.filter(published__isnull=False).order_by("-published")
        paginator = Paginator(qs, 6)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        context = {
            "news_list": page_obj.object_list,
            "is_paginated": page_obj.has_other_pages(),
            "page_obj": page_obj,
        }
    else:
        # Fallback sample data
        sample = [
            {"pk": 1, "title": "Scholarship applications open", "published": None, "excerpt": "Applications for 2026 are now open.", "featured_image": None},
            {"pk": 2, "title": "Selection criteria updated", "published": None, "excerpt": "We updated the selection criteria to be more inclusive.", "featured_image": None},
        ]
        context = {"news_list": sample, "is_paginated": False}

    return render(request, "applications/news.html", context)


def news_detail(request, pk):
    """
    News detail view. Uses News model if available; otherwise returns a sample item.
    """
    if News is not None:
        item = get_object_or_404(News, pk=pk)
        context = {"news": item}
    else:
        # Simple fallback
        sample_item = {"pk": pk, "title": f"Sample news item #{pk}", "published": None, "content": "<p>Sample content.</p>", "featured_image": None}
        context = {"news": sample_item}

    return render(request, "applications/news_detail.html", context)


def faq_view(request):
    faqs = FAQ.objects.all()
    return render(request, "applications/faq.html", {"faqs": faqs})

def terms_view(request):
    terms = PolicyPage.objects.filter(title="Terms & Conditions").first()
    return render(request, "applications/terms.html", {"terms": terms})

def privacy_view(request):
    privacy = PolicyPage.objects.filter(title="Privacy Policy").first()
    return render(request, "applications/privacy.html", {"privacy": privacy})

def about_view(request):
    return render(request, "applications/about.html")
# -- View Of Continuing Student --

def lookup_legacy(request):
    cfg = ApplicationConfig.get_solo()
    if cfg.rollover_due() or not cfg.legacy_lookup_enabled:
        return redirect("applications:continuing_application")  # your continuing route

    matches = None
    if request.method == "POST":
        form = LegacyLookupForm(request.POST)
        if form.is_valid():
            first_name = form.cleaned_data['first_name'].strip()
            surname = form.cleaned_data['surname'].strip()
            year = form.cleaned_data.get('year_of_study')

            filters = {
                "first_name__iexact": first_name,
                "surname__iexact": surname,
            }
            if year:
                filters["year_of_study"] = year

            matches = LegacyStudent.objects.filter(**filters)

            if not matches.exists():
                messages.warning(request, "No matching legacy record found. Please apply as a new student.")
    else:
        form = LegacyLookupForm()

    return render(request, "applications/lookup.html", {"matches": matches, "form": form})

@login_required
def confirm_legacy(request):
    legacy_id = request.POST.get("legacy_id") or request.GET.get("legacy_id")
    legacy = LegacyStudent.objects.filter(id=legacy_id).first()

    # Only go back to lookup if the legacy record truly doesn't exist
    if not legacy:
        messages.warning(request, "Legacy record not found. Please search again.")
        return redirect("applications:lookup_legacy")

    applicant = getattr(request.user, "applicantprofile", None)
    if not applicant:
        applicant = ApplicantProfile.objects.create(
            user=request.user,
            first_name=legacy.first_name.strip(),
            surname=legacy.surname.strip(),
        )

    if request.method == "POST":
        inst_id = request.POST.get("institution")
        course_id = request.POST.get("course")
        year_of_study = request.POST.get("year_of_study")

        if inst_id and course_id and year_of_study:
            inst = Institution.objects.filter(id=inst_id).first()
            course = Course.objects.filter(id=course_id, institution=inst).first()

            if inst and course:
                app = Application.objects.create(
                    applicant=applicant,
                    institution=inst,
                    course=course,
                    is_continuing=True,
                    year_of_study=year_of_study,
                    status=Application.STATUS_PENDING,
                    submission_date=timezone.now()
                )
                return redirect(reverse("applications:continue_application", args=[app.pk]))

            messages.error(request, "Invalid institution or course selection.")
        else:
            messages.error(request, "Please select institution, course, and year of study.")

        # Stay on selection page, keep legacy_id in context
        institutions = Institution.objects.all()
        courses = Course.objects.all()
        return render(request, "applications/select_institution_course.html", {
            "legacy": legacy,
            "institutions": institutions,
            "courses": courses,
        })

    # Initial GET → show selection form
    institutions = Institution.objects.all()
    courses = Course.objects.all()
    return render(request, "applications/select_institution_course.html", {
        "legacy": legacy,
        "institutions": institutions,
        "courses": courses,
    })


def courses_api(request):
    inst_id = request.GET.get("institution_id")
    if not inst_id:
        return JsonResponse([], safe=False)

    courses = Course.objects.filter(institution_id=inst_id).values("id", "name", "code")
    return JsonResponse(list(courses), safe=False)

@login_required
@transaction.atomic
def edit_continuing_application(request, pk):
    cfg = block_if_applications_closed(request)
    if cfg:
        return render(request, "applications/applications_closed.html", {"cfg": cfg})

    application = get_object_or_404(
        Application,
        pk=pk,
        applicant=request.user.applicantprofile,
        is_continuing=True
    )
    profile = request.user.applicantprofile

    if application.has_edited:
        messages.error(request, "You have already edited your application once.")
        return redirect("applications:continuing_dashboard")

    if request.method == "POST":
        profile_form = ContinuingProfileForm(request.POST, request.FILES, instance=profile)
        app_form = ContinuingApplicationForm(request.POST, request.FILES, instance=application)

        if profile_form.is_valid() and app_form.is_valid():
            profile_form.save()
            app_form.save()

            application.has_edited = True
            application.save(update_fields=["has_edited"])

            messages.success(request, "Your continuing application was updated successfully.")
            return redirect("applications:continuing_dashboard")

        messages.error(request, "Please correct the errors below.")
    else:
        profile_form = ContinuingProfileForm(instance=profile)
        app_form = ContinuingApplicationForm(instance=application)

    return render(request, "applications/edit_continuing_application.html", {
        "application": application,
        "profile": profile,
        "profile_form": profile_form,
        "form": app_form,  # template uses "form"
    })

@login_required
@transaction.atomic
def continue_application(request, pk):
    cfg = ApplicationConfig.get_solo()
    if cfg.is_closed_now():
        return applications_closed_response(request)

    application = get_object_or_404(
        Application,
        pk=pk,
        applicant=request.user.applicantprofile,
        is_continuing=True
    )
    profile = request.user.applicantprofile

    # Decide which application form to use based on config
    cfg = ApplicationConfig.get_solo()
    if cfg.rollover_due():
        ApplicationFormClass = ContinuingTranscriptOnlyForm
    else:
        ApplicationFormClass = ContinuingApplicationForm

    if request.method == "POST":
        profile_form = ContinuingProfileForm(request.POST, request.FILES, instance=profile)
        app_form = ApplicationFormClass(request.POST, request.FILES, instance=application)

        if profile_form.is_valid() and app_form.is_valid():
            # Save profile first
            profile_form.save()

            # Save application, syncing fields if needed
            app_obj = app_form.save(commit=False)
            if profile.active_student_id:
                app_obj.active_student_id = profile.active_student_id
            if request.user.email:
                app_obj.email = request.user.email
            app_obj.save()

            messages.success(request, "Profile and continuing application submitted successfully.")
            return redirect("applications:continuing_dashboard")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        profile_form = ContinuingProfileForm(instance=profile)
        app_form = ApplicationFormClass(instance=application)

    return render(request, "applications/continue_application.html", {
        "application": application,
        "profile": profile,
        "profile_form": profile_form,
        "app_form": app_form,
    })


class ContinuingApplicationUpdateView(UpdateView):
    model = ApplicantProfile
    form_class = ContinuingProfileForm
    template_name = "applications/edit_continuing_application.html"
    success_url = reverse_lazy("applications:continuing_dashboard")  # or override get_success_url

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Application saved successfully.")
        return response

    def form_invalid(self, form):
        # optional: log errors
        logger.debug("ContinuingApplicationForm invalid: %s", form.errors)
        return super().form_invalid(form)

def applications_closed_response(request):
    return render(request, "applications/applications_closed.html")

def block_if_applications_closed(request):
    cfg = ApplicationConfig.get_solo()
    if cfg.is_closed_now():
        return cfg
    return None