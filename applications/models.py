
# applications/models.py (cleaned / fixes)
from decimal import Decimal
from django.db import models, transaction
from institutions.models import Institution, Course
from django.conf import settings
from django.urls import reverse
from django.utils.text import slugify
from django.db.models import Sum
from django.utils import timezone
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.conf import settings
from django.db.models import Sum
from decimal import Decimal
from django.contrib.auth import get_user_model
from django import forms
from .validators import validate_upload

User = get_user_model()

class News(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    excerpt = models.CharField(max_length=500, blank=True)
    content = models.TextField()
    featured_image = models.ImageField(upload_to='news_images/', blank=True, null=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='news_items'
    )
    published = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-published', '-created_at']
        verbose_name = 'News'
        verbose_name_plural = 'News'

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:200]
            slug = base
            counter = 1
            while News.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('applications:news_detail', kwargs={'pk': self.pk})

class LegacyStudent(models.Model):
    first_name = models.CharField(max_length=100)
    surname = models.CharField(max_length=100)
    institution = models.CharField(max_length=200, blank=True)
    course = models.CharField(max_length=200, blank=True)
    # models.py (Application)

    YEAR_CHOICES = [
    (1, "Year 1"),
    (2, "Year 2"),
    (3, "Year 3"),
    (4, "Year 4"),
    (5, "Year 5"),
    ]

    year_of_study = models.IntegerField(choices=YEAR_CHOICES, null=True, blank=True)

    tuition_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.surname}"

class ApplicantProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    postal_address = models.TextField(blank=True)
    photo = models.ImageField(upload_to='profile_photos/', null=True, blank=True)
  
    # --- Personal Information ---
    first_name = models.CharField(max_length=100, blank=True)
    surname = models.CharField(max_length=100, blank=True)
    gender = models.CharField(max_length=10, choices=[('M', 'Male'), ('F', 'Female')], blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    nid_number = models.CharField(max_length=50, blank=True)
    grade12_certificate_number = models.CharField(max_length=50, blank=True)
    elementary_completed = models.BooleanField(default=False)
    primary_completed = models.BooleanField(default=False)
    secondary_school_name = models.CharField(max_length=150, blank=True)
    year_completed_grade12 = models.PositiveIntegerField(null=True, blank=True)
    tesas_category = models.CharField(
        max_length=10,
        choices=[('HECAS', 'HECAS'), ('AES', 'AES'), ('SS', 'SS')],
        blank=True
    )
    active_student_id = models.CharField(max_length=50, blank=True)

    # --- Father Information ---
    father_name = models.CharField(max_length=150, blank=True)
    father_occupation = models.CharField(max_length=100, blank=True)
    father_nationality = models.CharField(max_length=100, blank=True)
    father_province = models.CharField(max_length=100, blank=True)
    father_district = models.CharField(max_length=100, blank=True)
    father_llg = models.CharField(max_length=100, blank=True)
    father_village = models.CharField(max_length=100, blank=True)
    father_elementary_completed = models.BooleanField(default=False)
    father_primary_completed = models.BooleanField(default=False)
    father_highschool_completed = models.BooleanField(default=False)

    # --- Mother Information ---
    mother_name = models.CharField(max_length=150, blank=True)
    mother_occupation = models.CharField(max_length=100, blank=True)
    mother_nationality = models.CharField(max_length=100, blank=True)
    mother_province = models.CharField(max_length=100, blank=True)
    mother_district = models.CharField(max_length=100, blank=True)
    mother_llg = models.CharField(max_length=100, blank=True)
    mother_village = models.CharField(max_length=100, blank=True)
    mother_elementary_completed = models.BooleanField(default=False)
    mother_elementary_year = models.PositiveIntegerField(null=True, blank=True)
    mother_primary_completed = models.BooleanField(default=False)
    mother_primary_year = models.PositiveIntegerField(null=True, blank=True)
    mother_highschool_completed = models.BooleanField(default=False)
    mother_highschool_year = models.PositiveIntegerField(null=True, blank=True)

    # --- Additional Information ---
    current_residential_area = models.CharField(max_length=255, blank=True)
    duration_living_in = models.CharField(max_length=50, blank=True)
    current_district = models.CharField(max_length=100, blank=True)
    current_llg = models.CharField(max_length=100, blank=True)
    origin_province = models.CharField(max_length=100, blank=True)
    origin_district = models.CharField(max_length=100, blank=True)
    origin_ward = models.CharField(max_length=100, blank=True)
    residency_province = models.CharField(max_length=100, blank=True)
    residency_district = models.CharField(max_length=100, blank=True)
    residency_ward = models.CharField(max_length=100, blank=True)
    residency_years = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Application(models.Model):
    STATUS_PENDING = 'PENDING'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_GRADUATING = "GRADUATING"
    STATUS_PASSOUT = "PASSOUT"

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_GRADUATING, "Graduating"),
        (STATUS_PASSOUT, "Passout"),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    applicant = models.ForeignKey('ApplicantProfile', on_delete=models.CASCADE, related_name='applications')
    institution = models.ForeignKey(Institution, on_delete=models.PROTECT, related_name="applications")
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True)

    original_application = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='continuations'
    )

    is_continuing = models.BooleanField(default=False)
    has_edited = models.BooleanField(default=False)
    # models.py (Application)

    YEAR_CHOICES = [
    (1, "Year 1"),
    (2, "Year 2"),
    (3, "Year 3"),
    (4, "Year 4"),
    (5, "Year 5"),
    ]

    year_of_study = models.IntegerField(choices=YEAR_CHOICES, null=True, blank=True)


    # Continuing-specific fields
    active_student_id = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    current_address = models.TextField(blank=True, null=True)
   

    reviewer_note = models.TextField(blank=True, null=True)
    ai_summary = models.TextField(blank=True, null=True)

        # New applicant documents
    documents_pdf = models.FileField(
        upload_to="applications/documents/",
        blank=True,
        null=True,
        help_text="Upload all required documents as ONE PDF"
    )
    

    # Parent/student employment info (already present)
    parent_employed = models.BooleanField(default=False)
    parent_company = models.CharField(max_length=255, blank=True)
    parent_job_title = models.CharField(max_length=255, blank=True)
    parent_salary_range = models.CharField(max_length=100, blank=True)
    parent_income_source = models.CharField(max_length=255, blank=True)
    parent_annual_income = models.CharField(max_length=100, blank=True)

    student_employed = models.BooleanField(default=False)
    student_company = models.CharField(max_length=255, blank=True)
    student_job_title = models.CharField(max_length=255, blank=True)
    student_salary_range = models.CharField(max_length=100, blank=True)

    # Origin/residency info
    origin_province = models.CharField(max_length=100, blank=True)
    origin_district = models.CharField(max_length=100, blank=True)
    origin_ward = models.CharField(max_length=100, blank=True)
    residency_province = models.CharField(max_length=100, blank=True)
    residency_district = models.CharField(max_length=100, blank=True)
    residency_ward = models.CharField(max_length=100, blank=True)
    residency_years = models.CharField(max_length=3, blank=True)

    submission_date = models.DateTimeField(auto_now_add=True)
    last_cycle_started_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-submission_date']
        permissions = [("view_financials", "Can view financial details for applications")]

    def __str__(self):
        username = getattr(self.applicant, 'user', None)
        username_str = (getattr(username, 'get_full_name', None) and username.get_full_name()) or getattr(username, 'username', None) or "unknown"
        return f"Application #{self.id} for {username_str} — {self.get_status_display()}"

    @property
    def unique_id(self):
        year = getattr(self.submission_date, 'year', timezone.now().year)
        institution_code = (getattr(self.institution, 'code', '') or "").upper()
        course_code = (getattr(self.course, 'code', '') or "").upper()
        return f"{year}-{institution_code or 'NOINST'}-{course_code or 'NOCOURSE'}-{self.id}"

    @property
    def latest_review_status(self):
        latest = self.reviews.order_by("-created_at").first()
        return latest.status if latest else self.status

    @property
    def total_paid(self):
        from finance.models import Payment
        return Payment.objects.filter(
            application=self,
            status=Payment.STATUS_PAID
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    @property
    def total_committed(self):
        from finance.models import Payment
        return Payment.objects.filter(
            application=self,
            status=Payment.STATUS_COMMITTED
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")


    @property
    def outstanding_balance(self):
        if not self.course or self.course.total_tuition_fee is None:
            return Decimal("0.00")
        total_fee = Decimal(self.course.total_tuition_fee or Decimal("0.00"))
        paid = Decimal(self.total_paid or Decimal("0.00"))
        bal = total_fee - paid
        return bal if bal > 0 else Decimal("0.00")

    @property
    def payment_status(self):
        if not self.course or self.course.total_tuition_fee is None:
            return "Fee Not Set"
        total_fee = Decimal(self.course.total_tuition_fee or Decimal("0.00"))
        paid = Decimal(self.total_paid or Decimal("0.00"))
        if paid >= total_fee:
            return "Fully Paid"
        if paid > 0:
            return "Partially Paid"
        return "Unpaid"

    def set_status(self, new_status, reviewer=None, note=None, notify=True):
        new_status = str(new_status).upper()
        valid_keys = {k for k, _ in self.STATUS_CHOICES}
        if new_status not in valid_keys:
            raise ValueError(f"Invalid status: {new_status}")

        old_status = self.status
        if old_status == new_status:
            return None

        with transaction.atomic():
            self.status = new_status
            if note:
                self.reviewer_note = note
            self.save(update_fields=['status', 'reviewer_note', 'updated_at'])

            review_status = {
                self.STATUS_APPROVED: ApplicationReview.STATUS_APPROVED,
                self.STATUS_REJECTED: ApplicationReview.STATUS_REJECTED,
            }.get(new_status, ApplicationReview.STATUS_PENDING)

            review = ApplicationReview.objects.create(
                application=self,
                reviewer=reviewer,
                note=note or f"Status changed to {new_status}",
                status=review_status
            )

        return review

    def can_start_continuing_cycle(self):
        if not self.course or not self.year_of_study:
            return False
        if self.status != self.STATUS_APPROVED:
            return False
        max_years = getattr(self.course, 'years_of_study', None)
        if max_years is not None and self.year_of_study >= max_years:
            return False
        next_year = self.year_of_study + 1
        exists = Application.objects.filter(
            original_application=self,
            is_continuing=True,
            year_of_study=next_year
        ).exists()
        return not exists

    def create_continuing_application(self, when=None):
        if when is None:
            when = timezone.now()
        if not self.can_start_continuing_cycle():
            return None

        next_year = self.year_of_study + 1
        with transaction.atomic():
            existing = Application.objects.filter(
                original_application=self,
                is_continuing=True,
                year_of_study=next_year
            ).first()
            if existing:
                return existing

            cont = Application.objects.create(
                applicant=self.applicant,
                institution=self.institution,
                course=self.course,
                original_application=self,
                is_continuing=True,
                year_of_study=next_year,
                status=self.STATUS_PENDING,
                last_cycle_started_at=when,
            )
            self.last_cycle_started_at = when
            self.save(update_fields=['last_cycle_started_at'])
            return cont

    def increment_year_and_check_graduation(self):
        if not self.course:
            return False
        current = self.year_of_study or 0
        max_years = getattr(self.course, 'years_of_study', None)
        if max_years is None:
            return False

        if current >= max_years:
            return False

        self.year_of_study = current + 1
        if self.year_of_study >= max_years:
            self.status = self.STATUS_GRADUATING
        self.save(update_fields=['year_of_study', 'status', 'updated_at'])
        return True

    def mark_passout(self):
        self.status = self.STATUS_PASSOUT
        self.save(update_fields=['status', 'updated_at'])

    @property
    def is_final_year(self):
        if not self.course or not self.year_of_study:
            return False
        return self.year_of_study >= getattr(self.course, 'years_of_study', 0)

class ApplicationConfig(models.Model):
    applications_open = models.BooleanField(default=True)   # admin “button”
    close_at = models.DateTimeField(null=True, blank=True)  # optional closing datetime

    # rollover controls
    rollover_at = models.DateTimeField(null=True, blank=True)  # set to Dec 1, 2026
    legacy_lookup_enabled = models.BooleanField(default=True)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def is_closed_now(self):
        if not self.applications_open:
            return True
        if self.close_at and timezone.now() >= self.close_at:
            return True
        return False

    def rollover_due(self):
        return bool(self.rollover_at and timezone.now() >= self.rollover_at)


class ApplicationReview(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_NEEDS_INFO = 'needs_info'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_NEEDS_INFO, 'Needs Info'),
    ]

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='application_reviews')
    note = models.TextField(blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    decision_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Application Review"
        verbose_name_plural = "Application Reviews"
        #unique_together = ('application', 'reviewer')

    def save(self, *args, **kwargs):
        if self.status in {self.STATUS_APPROVED, self.STATUS_REJECTED} and not self.decision_date:
            self.decision_date = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        reviewer_name = getattr(self.reviewer, 'username', None) or "Unknown Reviewer"
        return f"Review by {reviewer_name} on Application {self.application.id} [{self.get_status_display()}]"


@receiver(post_save, sender=ApplicationReview)
def application_review_post_save(sender, instance, created, **kwargs):
    try:
        # TODO: enqueue notification task, e.g. send_application_status_email.delay(instance.pk)
        pass
    except Exception as exc:
        # Do not silently swallow — at minimum log
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Error in application_review_post_save: %s", exc)


class FAQ(models.Model):
    question = models.CharField(max_length=255)
    answer = models.TextField()

    def __str__(self):
        return self.question


class PolicyPage(models.Model):
    title = models.CharField(max_length=100)
    content = models.TextField()

    def __str__(self):
        return self.title

# new model - 16/2/26 - migrate 2025 data)


class EligibleStudent2025(models.Model):
    first_name = models.CharField(max_length=120)
    surname = models.CharField(max_length=120)
    gender = models.CharField(max_length=10, blank=True)
    institution = models.CharField(max_length=255)
    course = models.CharField(max_length=255, blank=True)
    tuition_fee = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    district = models.CharField(max_length=120, blank=True)
    year_of_study = models.CharField(max_length=50, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["first_name", "surname"]),
            models.Index(fields=["institution"]),
        ]

    def __str__(self):
        return f"{self.first_name} {self.surname} - {self.institution}"
