from django.db import models
from django.core.validators import RegexValidator
from django.apps import apps
from decimal import Decimal


class Institution(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(
        max_length=10,
        unique=True,
        default='411-00',
        validators=[RegexValidator(r'^[A-Z0-9\-]+$', 'Only letters, numbers and hyphens allowed')]
    )
    location = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    # Treasury/Finance Fields
    vendor_code = models.CharField(max_length=50, blank=True, null=True, help_text="IFMS Vendor Code")
    tin = models.CharField(max_length=50, blank=True, null=True, help_text="Taxpayer Identification Number")

    # Bank account details
    account_name = models.CharField(max_length=255, blank=True, null=True)
    account_number = models.CharField(max_length=50, blank=True, null=True)
    bank = models.CharField(max_length=100, blank=True, null=True)
    branch = models.CharField(max_length=100, blank=True, null=True)
    account_type = models.CharField(max_length=20, blank=True, null=True, choices=[('CHEQ', 'Cheque'), ('SAV', 'Savings')])

    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("INACTIVE", "Inactive"),
        ("SUSPENDED", "Suspended"),
    ]
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="ACTIVE")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code or 'No Code'})"

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.upper()
        super().save(*args, **kwargs)

    # ----- convenience accessors -----
    def applications_qs(self):
        from applications.models import Application
        return Application.objects.filter(institution=self)

    def pending_applications(self):
        Application = apps.get_model("applications", "Application")
        return self.applications_qs().filter(status=Application.STATUS_PENDING)

    def selected_applications(self):
        from applications.models import Application
        return self.applications_qs().filter(status=Application.STATUS_APPROVED)

    def rejected_applications(self):
        Application = apps.get_model("applications", "Application")
        return self.applications_qs().filter(status=Application.STATUS_REJECTED)

    def total_payments(self):
        from finance.models import Payment
        return Payment.objects.filter(application__institution=self).total_amount()


class Course(models.Model):
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name='courses')
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=10)  # manually assigned, e.g. "CS", "EE", "ACC"
    years_of_study = models.PositiveIntegerField(default=4)
    total_tuition_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    class Meta:
        unique_together = ('institution', 'code')  # ensures no duplicate course codes within the same institution

    def __str__(self):
        return f"{self.code} - {self.name} at {self.institution.name}"



 