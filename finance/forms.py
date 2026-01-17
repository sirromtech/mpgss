# finance/forms.py
from django import forms
from django.utils import timezone

from .models import Payment, BudgetVote, FillablePDFTemplate


class PaymentCreateForm(forms.ModelForm):
    """
    Create a Payment record (FF3 commitment or FF4 paid), linked to an Application and BudgetVote.
    """
    class Meta:
        model = Payment
        fields = [
            "application",
            "budget_vote",
            "amount",
            "status",
            "payment_date",
            "vendor_code",
            "vote_item_code",
            "section_32_officer",
            "form11_identifier",
            "batch_number",
            "cheque_number",
            "treasury_release_date",
        ]
        widgets = {
            "payment_date": forms.DateInput(attrs={"type": "date"}),
            "treasury_release_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        payment_date = cleaned.get("payment_date")
        treasury_release_date = cleaned.get("treasury_release_date")

        # sensible defaults
        if status == Payment.STATUS_COMMITTED and not payment_date:
            cleaned["payment_date"] = timezone.localdate()

        if status == Payment.STATUS_PAID and not treasury_release_date:
            cleaned["treasury_release_date"] = timezone.localdate()

        return cleaned


class PaymentUpdateForm(forms.ModelForm):
    """
    Update administrative fields without changing core linkage.
    """
    class Meta:
        model = Payment
        fields = [
            "amount",
            "status",
            "payment_date",
            "vendor_code",
            "vote_item_code",
            "section_32_officer",
            "form11_identifier",
            "batch_number",
            "cheque_number",
            "treasury_release_date",
        ]
        widgets = {
            "payment_date": forms.DateInput(attrs={"type": "date"}),
            "treasury_release_date": forms.DateInput(attrs={"type": "date"}),
        }


class BudgetVoteForm(forms.ModelForm):
    class Meta:
        model = BudgetVote
        fields = ["vote_code", "description", "allocation_amount", "fiscal_year"]


class FillablePDFTemplateForm(forms.ModelForm):
    class Meta:
        model = FillablePDFTemplate
        fields = ["name", "template_type", "template_id", "description"]
