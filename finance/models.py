# finance/models.py
from decimal import Decimal
from django.db import models, transaction
from django.db.models import Sum
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone

User = get_user_model()


class BudgetVote(models.Model):
    vote_code = models.CharField(max_length=50, db_index=True)
    description = models.CharField(max_length=200)
    allocation_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    fiscal_year = models.IntegerField(default=2025)

    class Meta:
        unique_together = ("vote_code", "fiscal_year")
        ordering = ("-fiscal_year", "vote_code")

    def __str__(self):
        return f"{self.vote_code} ({self.fiscal_year})"

    @property
    def committed_amount(self):
        # COMMITTED only (not PAID, not CANCELLED)
        total = self.payments.filter(status=Payment.STATUS_COMMITTED).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")
        return Decimal(total)

    @property
    def paid_amount(self):
        total = self.payments.filter(status=Payment.STATUS_PAID).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")
        return Decimal(total)

    @property
    def remaining_balance(self):
        # Allocation - (Committed + Paid)
        return Decimal(self.allocation_amount) - self.committed_amount



class PaymentQuerySet(models.QuerySet):
    def committed(self):
        return self.filter(status=Payment.STATUS_COMMITTED)

    def paid(self):
        return self.filter(status=Payment.STATUS_PAID)

    def cancelled(self):
        return self.filter(status=Payment.STATUS_CANCELLED)

    def total_amount(self):
        return self.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")


class Payment(models.Model):
    STATUS_COMMITTED = "COMMITTED"
    STATUS_PAID = "PAID"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_COMMITTED, "Committed (FF3)"),
        (STATUS_PAID, "Paid/Processed (FF4)"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    application = models.ForeignKey(
        "applications.Application", on_delete=models.CASCADE, related_name="payments"
    )
    budget_vote = models.ForeignKey(
        BudgetVote, on_delete=models.PROTECT, null=True, blank=True, related_name="payments"
    )

    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_date = models.DateField(null=True, blank=True)

    batch_number = models.CharField(max_length=50, blank=True)
    cheque_number = models.CharField(max_length=50, null=True, blank=True)
    vendor_code = models.CharField(max_length=50, null=True, blank=True)
    form11_identifier = models.CharField(max_length=128, blank=True)
    section_32_officer = models.CharField(max_length=255, blank=True)
    vote_item_code = models.CharField(max_length=64, blank=True)
    treasury_release_date = models.DateField(null=True, blank=True)

    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_COMMITTED, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PaymentQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["batch_number"]),
            models.Index(fields=["vendor_code"]),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gt=0), name="payment_amount_gt_0"),
        ]

    def __str__(self):
        inst = getattr(self.application, "institution", None)
        inst_label = inst.name if inst else "Unknown Institution"
        return f"PGK {self.amount} - {inst_label} ({self.status})"

    @transaction.atomic
    def commit(self, user=None):
        if self.status != self.STATUS_COMMITTED:
            raise ValueError("Only payments in COMMITTED state can be re-committed.")
        if self.budget_vote:
            if self.budget_vote.remaining_balance < self.amount:
                raise ValueError("Insufficient allocation for this commitment.")
        self.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(user=user, action="Committed (FF3)", payment=self)
        return self

    @transaction.atomic
    def mark_paid(self, user=None, treasury_date=None, batch_number=None):
        if self.status == self.STATUS_PAID:
            return self
        self.status = self.STATUS_PAID
        self.treasury_release_date = treasury_date or self.treasury_release_date
        self.batch_number = batch_number or self.batch_number
        self.updated_at = timezone.now()
        self.save(update_fields=["status", "treasury_release_date", "batch_number", "updated_at"])
        AuditLog.objects.create(user=user, action="Marked as PAID (FF4/Treasury)", payment=self)
        return self

    @transaction.atomic
    def cancel(self, user=None, reason=None):
        if self.status == self.STATUS_CANCELLED:
            return self
        self.status = self.STATUS_CANCELLED
        self.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(user=user, action="Cancelled payment", payment=self, budget_vote=self.budget_vote, notes=reason or "")
        return self


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=150)
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True)
    budget_vote = models.ForeignKey(BudgetVote, on_delete=models.CASCADE, null=True, blank=True, related_name="audit_logs")
    timestamp = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-timestamp",)

    def __str__(self):
        user_label = self.user.get_username() if self.user else "System"
        return f"{self.timestamp:%Y-%m-%d %H:%M} - {user_label} - {self.action}"


class FillablePDFTemplate(models.Model):
    TEMPLATE_TYPES = [("FF3", "FF3 - Commitment"), ("FF4", "FF4 - Expenditure")]
    name = models.CharField(max_length=150)
    template_type = models.CharField(max_length=4, choices=TEMPLATE_TYPES)
    template_id = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("template_type", "template_id")
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.name} ({self.template_type})"


class GeneratedPDF(models.Model):
    REPORT_STATUS = [("READY", "Ready"),("FAILED", "Failed"),("PENDING", "Pending"),("PROCESSING", "Processing")]
    template = models.ForeignKey(FillablePDFTemplate, on_delete=models.PROTECT)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, null=True, blank=True, related_name="generated_pdfs")
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # ✅ needed (your views/admin expect it)
    file = models.FileField(upload_to="generated_pdfs/%Y/%m/%d/", null=True, blank=True)
    status = models.CharField(max_length=10, choices=REPORT_STATUS, default="PENDING")
    external_id = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-generated_at",)

    def __str__(self):
        payment_label = f"{self.payment.pk}" if self.payment else "bulk"
        return f"{self.template.template_type} - {payment_label} - {self.generated_at:%Y-%m-%d %H:%M}"


class SignedPDF(models.Model):
    generated_pdf = models.ForeignKey(GeneratedPDF, on_delete=models.CASCADE, related_name="signed_versions")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to="signed_pdfs/%Y/%m/%d/")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-uploaded_at",)

    def __str__(self):
        return f"SignedPDF {self.id} for GeneratedPDF {self.generated_pdf_id}"


class PDFAudit(models.Model):
    ACTION_CHOICES = [
        ("GENERATED", "Generated"),
        ("VIEWED", "Viewed"),
        ("DOWNLOADED", "Downloaded"),
        ("SIGNED_UPLOADED", "Signed Uploaded"),
        ("SAVED_EDIT", "Saved Edited"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    generated_pdf = models.ForeignKey(GeneratedPDF, on_delete=models.CASCADE, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-timestamp",)

    def __str__(self):
        user_label = self.user.get_username() if self.user else "System"
        return f"{self.timestamp:%Y-%m-%d %H:%M} - {user_label} - {self.action}"
