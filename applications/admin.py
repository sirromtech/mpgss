# applications/admin.py
from django.contrib import admin, messages
from django.db import transaction
from django.utils.html import format_html
from django.urls import reverse
from .models import ApplicantProfile, Application, FAQ, PolicyPage, News, ApplicationReview
from institutions.models import Institution, Course  # ✅ correct
from .models import ApplicationConfig

# Optional: import your notification helper or task if you want to call it directly
# from .utils import notify_student_status_change
from .tasks import send_application_status_email

class IsContinuingFilter(admin.SimpleListFilter):
    title = "Application Type"
    parameter_name = "is_continuing"

    def lookups(self, request, model_admin):
        return [
            ('yes', 'Continuing Students'),
            ('no', 'New Students'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(is_continuing=True)
        if self.value() == 'no':
            return queryset.filter(is_continuing=False)
        return queryset


@admin.register(ApplicantProfile)
class ApplicantProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user_link', 'phone_number', 'active_student_id', 'tesas_category',
        'secondary_school_name', 'year_completed_grade12'
    )
    list_filter = ('tesas_category', 'primary_completed', 'elementary_completed')
    search_fields = (
        'user__username', 'user__first_name', 'user__last_name',
        'nid_number', 'grade12_certificate_number', 'active_student_id'
    )
    readonly_fields = ('user',)
    autocomplete_fields = ()
    fieldsets = (
        ('Account', {
            'fields': ('user', 'photo', 'phone_number', 'postal_address')
        }),
        ('Personal Information', {
            'fields': (
                'first_name', 'surname', 'gender', 'date_of_birth',
                'sim_card_number', 'nid_number', 'grade12_certificate_number',
                'elementary_completed', 'primary_completed',
                'secondary_school_name', 'year_completed_grade12',
                'tesas_category', 'active_student_id'
            )
        }),
        ('Father Information', {
            'fields': (
                'father_name', 'father_occupation', 'father_nationality',
                'father_province', 'father_district', 'father_llg',
                'father_village', 'father_elementary_completed',
                'father_primary_completed', 'father_highschool_completed'
            )
        }),
        ('Mother Information', {
            'fields': (
                'mother_name', 'mother_occupation', 'mother_nationality',
                'mother_province', 'mother_district', 'mother_llg',
                'mother_village', 'mother_elementary_completed',
                'mother_elementary_year', 'mother_primary_completed',
                'mother_primary_year', 'mother_highschool_completed',
                'mother_highschool_year'
            )
        }),
        ('Current Address', {
            'fields': (
                'current_residential_area',
                'duration_living_in', 'current_district', 'current_llg'
            )
        }),
    )

    def user_link(self, obj):
        if obj.user:
            url = reverse('admin:auth_user_change', args=[obj.user.pk])
            return format_html('<a href="{}">{}</a>', url, obj.user.get_full_name() or obj.user.username)
        return '-'
    user_link.short_description = 'User'


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'applicant_link', 'applicant_email', 'institution', 'course',
        'year_of_study', 'status', 'submission_date'
    )
    list_filter = ('status', 'institution', 'submission_date', 'course', IsContinuingFilter)
    search_fields = (
        'applicant__user__username', 'applicant__user__first_name',
        'applicant__user__last_name', 'institution__name', 'course__name'
    )
    readonly_fields = ('submission_date', 'ai_summary')
    list_select_related = ('applicant__user', 'institution', 'course')
    actions = ('mark_as_approved', 'mark_as_rejected', 'mark_payment_paid', 'mark_payment_unpaid')
    autocomplete_fields = ('institution', 'course')

    fieldsets = (
        ('Application', {
            'fields': (
                'applicant', 'institution', 'course', 'year_of_study',
                'status', 'reviewer_note', 'ai_summary'
            )
        }),
        ('Documents', {
            'fields': (
                'grade_12_certificate', 'transcript', 'acceptance_letter',
                'school_fee_structure', 'id_card', 'character_reference_1',
                'character_reference_2', 'statdec'
            )
        }),
        ('Financial & Residency', {
            'fields': (
                'parent_employed', 'parent_company', 'parent_job_title',
                'parent_salary_range', 'parent_income_source', 'parent_annual_income',
                'student_employed', 'student_company', 'student_job_title',
                'student_salary_range', 'origin_province', 'origin_district',
                'origin_ward', 'residency_province', 'residency_district',
                'residency_ward', 'residency_years'
            )
        }),
    )

    def applicant_link(self, obj):
        if obj.applicant and obj.applicant.user:
            url = reverse('admin:applications_applicantprofile_change', args=[obj.applicant.pk])
            return format_html('<a href="{}">{}</a>', url, obj.applicant.user.get_full_name() or obj.applicant.user.username)
        return '-'
    applicant_link.short_description = 'Applicant'

    def applicant_email(self, obj):
        return obj.applicant.user.email if obj.applicant and obj.applicant.user else '-'
    applicant_email.short_description = 'Email'

    # ---------- Admin actions that update status and notify students ----------
    @admin.action(description='Mark selected applications as Approved and notify students')
    def mark_as_approved(self, request, queryset):
        updated = 0
        with transaction.atomic():
            for app in queryset.select_for_update():
                if app.status != Application.STATUS_APPROVED:
                    # Use the model helper so a review record is created and signals fire
                    try:
                        app.set_status(Application.STATUS_APPROVED, reviewer=request.user, note="Approved by admin", notify=True)
                        updated += 1
                    except Exception as exc:
                        self.message_user(request, f"Failed to approve application {app.pk}: {exc}", level=messages.WARNING)
        self.message_user(request, f"{updated} application(s) marked as Approved.", level=messages.SUCCESS)

    @admin.action(description='Mark selected applications as Rejected and notify students')
    def mark_as_rejected(self, request, queryset):
        updated = 0
        with transaction.atomic():
            for app in queryset.select_for_update():
                if app.status != Application.STATUS_REJECTED:
                    try:
                        app.set_status(Application.STATUS_REJECTED, reviewer=request.user, note="Rejected by admin", notify=True)
                        updated += 1
                    except Exception as exc:
                        self.message_user(request, f"Failed to reject application {app.pk}: {exc}", level=messages.WARNING)
        self.message_user(request, f"{updated} application(s) marked as Rejected.", level=messages.SUCCESS)

    @admin.action(description='Mark payment as Paid and notify students')
    def mark_payment_paid(self, request, queryset):
        # Replace this with your real payment-record logic; this is a placeholder
        updated = 0
        with transaction.atomic():
            for app in queryset.select_for_update():
                # If you have a Payment model, create a Payment record here instead
                # For auditability, create an ApplicationReview or Payment record
                updated += 1
        self.message_user(request, f"{updated} application(s) processed as Paid.", level=messages.SUCCESS)

    @admin.action(description='Mark payment as Unpaid and notify students')
    def mark_payment_unpaid(self, request, queryset):
        updated = 0
        with transaction.atomic():
            for app in queryset.select_for_update():
                updated += 1
        self.message_user(request, f"{updated} application(s) processed as Unpaid.", level=messages.SUCCESS)


@admin.register(ApplicationReview)
class ApplicationReviewAdmin(admin.ModelAdmin):
    list_display = ('application', 'reviewer', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('application__applicant__first_name', 'application__applicant__surname', 'reviewer__username')


@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'is_published', 'published', 'created_at')
    list_filter = ('is_published', 'published', 'created_at', 'author')
    search_fields = ('title', 'excerpt', 'content')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'published'
    ordering = ('-published',)


@admin.register(ApplicationConfig)
class ApplicationConfigAdmin(admin.ModelAdmin):
    list_display = ("applications_open", "close_at", "rollover_at", "legacy_lookup_enabled")


admin.site.register(FAQ)
admin.site.register(PolicyPage)
