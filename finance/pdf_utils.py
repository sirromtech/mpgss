# finance/pdf_utils.py
import os
import tempfile
import requests

from django.conf import settings
from django.core.files import File
from django.utils import timezone

from .models import GeneratedPDF


def _safe_name(payment):
    """
    Best-effort label for applicant.
    """
    try:
        user = payment.application.applicant.user
        full = user.get_full_name()
        return full if full else user.username
    except Exception:
        return f"Application {getattr(getattr(payment, 'application', None), 'pk', '')}".strip() or "Unknown Applicant"


def _write_pdf_to_gen(gen, pdf_bytes, filename_prefix="ff"):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    try:
        tmp.write(pdf_bytes)
        tmp.flush()
        tmp.close()
        with open(tmp.name, "rb") as f:
            gen.file.save(f"{filename_prefix}_{gen.id}.pdf", File(f), save=True)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def generate_fillable_pdf_for_payment(generated_pdf_id, flatten=False, timeout=60):
    """
    Calls external 2pdf service to fill a template for a specific GeneratedPDF row.

    - generated_pdf_id: ID of GeneratedPDF
    - flatten: whether to flatten the PDF fields (True = non-editable)
    - timeout: seconds for API calls
    """
    gen = GeneratedPDF.objects.select_related("payment__application__institution", "template").get(pk=generated_pdf_id)

    if not gen.payment:
        gen.status = "FAILED"
        gen.notes = "No payment linked to this GeneratedPDF"
        gen.save(update_fields=["status", "notes"])
        return False

    payment = gen.payment
    template = gen.template

    api_key = getattr(settings, "TWO_PDF_API_KEY", None)
    api_url = getattr(settings, "TWO_PDF_API_URL", None)

    if not api_url:
        gen.status = "FAILED"
        gen.notes = "TWO_PDF_API_URL is not configured"
        gen.save(update_fields=["status", "notes"])
        return False

    # Safe values
    applicant_name = _safe_name(payment)
    institution_name = ""
    try:
        institution_name = payment.application.institution.name if payment.application and payment.application.institution else ""
    except Exception:
        institution_name = ""

    payment_date = payment.payment_date or timezone.localdate()

    # Map YOUR template field keys → your values
    field_map = {
        "requisition_no": payment.form11_identifier or "",  # or payment.id/batch if that’s your rule
        "applicant_name": applicant_name,
        "institution": institution_name,
        "amount": f"{payment.amount:.2f}",
        "payment_date": payment_date.strftime("%d/%m/%Y"),
        "budget_vote": payment.budget_vote.vote_code if payment.budget_vote else (payment.vote_item_code or ""),
        "vendor_code": payment.vendor_code or "",
        "batch_number": payment.batch_number or "",
    }

    payload = {
        "template_id": template.template_id,
        "fields": field_map,
        "flatten": bool(flatten),
    }

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        gen.status = "PENDING"
        gen.notes = ""
        gen.save(update_fields=["status", "notes"])

        resp = requests.post(api_url, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()

        ctype = (resp.headers.get("Content-Type") or "").lower()

        # Case 1: API returns PDF bytes directly
        if "application/pdf" in ctype:
            _write_pdf_to_gen(gen, resp.content, filename_prefix=template.template_type.lower())
            gen.status = "READY"
            gen.save(update_fields=["status"])
            return True

        # Case 2: API returns JSON with a URL
        data = resp.json()
        file_url = data.get("file_url") or data.get("url")
        if not file_url:
            gen.status = "FAILED"
            gen.notes = f"No file_url/url returned by PDF service. Response: {data}"
            gen.save(update_fields=["status", "notes"])
            return False

        # Download the pdf
        r2 = requests.get(file_url, timeout=timeout)
        r2.raise_for_status()

        _write_pdf_to_gen(gen, r2.content, filename_prefix=template.template_type.lower())

        gen.status = "READY"
        gen.external_id = data.get("id", "") or gen.external_id
        gen.save(update_fields=["status", "external_id"])
        return True

    except Exception as exc:
        gen.status = "FAILED"
        gen.notes = str(exc)
        gen.save(update_fields=["status", "notes"])
        return False
