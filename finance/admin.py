# finance/admin.py
from django.contrib import admin, messages
from django.db import transaction
from django.urls import path, reverse
from django.shortcuts import get_object_or_404, HttpResponseRedirect
from django.utils.html import format_html
from django.utils import timezone

from .models import (
    Payment,
    BudgetVote,
    AuditLog,
    
    FillablePDFTemplate,
    GeneratedPDF,
    SignedPDF,
    PDFAudit,
)

from .tasks import process_generated_pdf


# ---------------- PDF admin models ----------------

@admin.register(SignedPDF)
class SignedPDFAdmin(admin.ModelAdmin):
    list_display = ("id", "generated_pdf", "uploaded_by", "uploaded_at", "file")
    readonly_fields = ("uploaded_at",)
    search_fields = ("generated_pdf__id", "uploaded_by__username")


@admin.register(PDFAudit)
class PDFAuditAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "generated_pdf")
    readonly_fields = ("timestamp", "user", "action", "generated_pdf", "notes")
    search_fields = ("user__username", "action", "generated_pdf__id")


def queue_for_processing(modeladmin, request, queryset):
    """Admin action to queue GeneratedPDF rows for background processing."""
    count = 0
    for gen in queryset.filter(status__in=["PENDING", "FAILED"]):
        process_generated_pdf.delay(gen.id)
        count += 1
    modeladmin.message_user(request, f"Queued {count} PDFs for processing.")
queue_for_processing.short_description = "Queue selected PDFs for Celery processing"


# ---------------- Payment admin with actions ----------------

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "application",
        "vendor_code",
        "amount",
        "status",
        "budget_vote",
        "payment_date",
        "pdf_actions",
    )
    list_filter = ("status", "budget_vote", "application__institution")
    search_fields = (
        "application__applicant__user__username",
        "application__applicant__user__first_name",
        "application__applicant__user__last_name",
        "vendor_code",
    )

    actions = [
        "action_commit_payments",
        "action_mark_payments_paid",
        "action_cancel_payments",
        "generate_ff3_for_selected",
        "generate_ff4_for_selected",

    ]


    # --- Admin actions: commit / mark paid / cancel ---


    def action_commit_payments(self, request, queryset):
        committed = skipped = errors = 0
        payment_ids = list(queryset.values_list("id", flat=True))

        # Ensure this is inside the method body
        with transaction.atomic():
            qs = Payment.objects.select_for_update().filter(id__in=payment_ids)

            for payment in qs:
                try:
                    if payment.status == Payment.STATUS_CANCELLED:
                        skipped += 1
                        continue

                    # commit() already logs AuditLog in your model
                    payment.commit(user=request.user)
                    committed += 1

                except Exception:
                    errors += 1
                    logger = logging.getLogger(__name__)
                    logger.exception("Commit failed for payment %s", payment.id)

        msg = f"{committed} committed."
        if skipped:
            msg += f" {skipped} skipped (cancelled)."
        if errors:
            msg += f" {errors} failed."

        self.message_user(request, msg, level=messages.INFO)

    def action_mark_payments_paid(self, request, queryset):
        """
        Mark selected payments as PAID (FF4/Treasury).
        Optionally accepts 'batch_number' via POST if provided by a custom action form.
        """
        paid = 0
        skipped = 0
        errors = 0
        batch_number = request.POST.get("batch_number", "")  # only present if custom form used
        for payment in queryset.select_for_update():
            try:
                with transaction.atomic():
                    if payment.status == Payment.STATUS_PAID:
                        skipped += 1
                        continue
                    try:
                        payment.mark_paid(user=request.user, treasury_date=timezone.localdate(), batch_number=batch_number or None)
                    except Exception:
                        payment.status = Payment.STATUS_PAID
                        payment.treasury_release_date = payment.treasury_release_date or timezone.localdate()
                        if batch_number:
                            payment.batch_number = batch_number
                        payment.save(update_fields=["status", "treasury_release_date", "batch_number", "updated_at"])
                        AuditLog.objects.create(user=request.user, action="Marked as PAID (FF4/Treasury)", payment=payment, budget_vote=payment.budget_vote, notes=f"Batch {batch_number}" if batch_number else "")
                    paid += 1
            except Exception:
                errors += 1
        msg = f"{paid} payment(s) marked as PAID."
        if skipped:
            msg += f" {skipped} skipped (already PAID)."
        if errors:
            msg += f" {errors} failed."
        self.message_user(request, msg, level=messages.INFO)
    action_mark_payments_paid.short_description = "Mark selected payments as PAID (FF4/Treasury)"

    def action_cancel_payments(self, request, queryset):
        """Cancel selected payments and create AuditLog entries."""
        cancelled = 0
        skipped = 0
        errors = 0
        for payment in queryset.select_for_update():
            try:
                with transaction.atomic():
                    if payment.status == Payment.STATUS_CANCELLED:
                        skipped += 1
                        continue
                    try:
                        payment.cancel(user=request.user, reason="Cancelled via admin")
                    except Exception:
                        payment.status = Payment.STATUS_CANCELLED
                        payment.save(update_fields=["status", "updated_at"])
                        AuditLog.objects.create(user=request.user, action="Cancelled payment", payment=payment, budget_vote=payment.budget_vote, notes="Cancelled via admin")
                    cancelled += 1
            except Exception:
                errors += 1
        msg = f"{cancelled} payment(s) cancelled."
        if skipped:
            msg += f" {skipped} skipped (already cancelled)."
        if errors:
            msg += f" {errors} failed."
        self.message_user(request, msg, level=messages.WARNING)
    action_cancel_payments.short_description = "Cancel selected payments"

    # --- PDF actions column and bulk generation ---

    def pdf_actions(self, obj):
        """Show link to view generated PDFs or quick generate action."""
        if obj.generated_pdfs.exists():
            link = reverse("admin:finance_generatedpdf_changelist") + f"?payment__id__exact={obj.id}"
            return format_html(
                '<a class="button" href="{}">Generate PDF</a>',
                reverse("admin:finance_generatedpdf_generate_pdf") + f"?payment_id={obj.id}"
                )

        # admin URL name 'finance_generate_pdf' is defined in GeneratedPDFAdmin.get_urls
        return format_html('<a class="button" href="{}">Generate PDF</a>', reverse("admin:finance_generate_pdf") + f"?payment_id={obj.id}")
    pdf_actions.short_description = "PDFs"
    

    def generate_ff3_for_selected(self, request, queryset):
        return self._bulk_generate(request, queryset, template_type="FF3")
    generate_ff3_for_selected.short_description = "Generate FF3 (fillable) for selected payments"

    def generate_ff4_for_selected(self, request, queryset):
        return self._bulk_generate(request, queryset, template_type="FF4")
    generate_ff4_for_selected.short_description = "Generate FF4 (fillable) for selected payments" 

def _bulk_generate(self, request, queryset, template_type):
    template = FillablePDFTemplate.objects.filter(template_type=template_type).first()
    if not template:
        self.message_user(
            request,
            f"No template configured for {template_type}",
            level=messages.ERROR
        )
        return

    created = 0
    skipped = 0

    for payment in queryset:
        exists = GeneratedPDF.objects.filter(
            payment=payment,
            template=template,
            status__in=["PENDING", "READY"]
        ).exists()
        if exists:
            skipped += 1
            continue

        GeneratedPDF.objects.create(
            template=template,
            payment=payment,
            generated_by=request.user,
            status="PENDING"
        )
        created += 1

    self.message_user(
        request,
        f"Created {created} {template_type} PDF(s). Skipped {skipped} existing.",
        level=messages.INFO
    )

# ---------------- FillablePDFTemplate and GeneratedPDF admin ----------------

@admin.register(FillablePDFTemplate)
class FillablePDFTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "template_type", "template_id", "created_at")
    search_fields = ("name", "template_id")


@admin.register(GeneratedPDF)
class GeneratedPDFAdmin(admin.ModelAdmin):
    list_display = ("id", "template", "payment", "generated_by", "generated_at", "status", "download_link")
    readonly_fields = ("generated_at",)
    actions = [queue_for_processing]

    # Add a small admin view to trigger generation for a single payment
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "generate-pdf/",
                self.admin_site.admin_view(self.generate_pdf_view),
                name="finance_generatedpdf_generate_pdf",
                ),

        ]
        return custom + urls

    def generate_pdf_view(self, request):
        """Admin view to trigger generation for a single payment (expects ?payment_id=...)."""
        payment_id = request.GET.get("payment_id")
        if not payment_id:
            self.message_user(request, "payment_id is required", level=messages.ERROR)
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", "/admin/"))

        payment = get_object_or_404(Payment, pk=payment_id)
        template = FillablePDFTemplate.objects.filter(template_type="FF4").first()
        if not template:
            self.message_user(request, "No FF4 template configured", level=messages.ERROR)
            return HttpResponseRedirect(request.META.get("HTTP_REFERER", "/admin/"))

        GeneratedPDF.objects.create(template=template, payment=payment, generated_by=request.user, status="PENDING")
        self.message_user(request, "PDF generation queued.")
        return HttpResponseRedirect(request.META.get("HTTP_REFERER", "/admin/"))

    def download_link(self, obj):
        if obj.file:
            return format_html('<a href="{}" target="_blank">Download</a>', obj.file.url)
        return "-"
    download_link.short_description = "Download"


# ---------------- BudgetVote, AuditLog, FinancialReport admin ----------------

@admin.register(BudgetVote)
class BudgetVoteAdmin(admin.ModelAdmin):
    list_display = ("vote_code", "description", "allocation_amount", "fiscal_year", "remaining_balance")
    search_fields = ("vote_code", "description")
    list_filter = ("fiscal_year",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "payment", "budget_vote")
    readonly_fields = ("timestamp", "user", "action", "payment", "budget_vote", "notes")
    list_filter = ("action", "user")
    search_fields = ("user__username", "action", "payment__id")


#@admin.register(FinancialReport)
#class FinancialReportAdmin(admin.ModelAdmin):
    #list_display = ("report_type", "generated_by", "generated_at", "file_path")
    #readonly_fields = ("report_type", "generated_by", "generated_at", "file_path")
    #list_filter = ("report_type", "generated_at")


# ---------------- Read-only admin for Scholarship Officers (optional) ----------------

class ScholarshipOfficerPaymentAdmin(PaymentAdmin):
    """View-only access for Scholarship Officers."""
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

# To register the read-only view for a specific group, uncomment and use:
# admin.site.register(Payment, ScholarshipOfficerPaymentAdmin)
