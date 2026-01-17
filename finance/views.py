# finance/views.py
import csv
import io
import os
import tempfile
import requests
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test, permission_required
from django.db import transaction
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views import generic

from .models import (
    Payment,
    FillablePDFTemplate,
    GeneratedPDF,
    PDFAudit,
    SignedPDF,
    BudgetVote,
)
from .permissions import section32_required
from .tasks import process_generated_pdf
from django.utils.dateparse import parse_date
from django.core.files import File
from django.db.models import Sum

User = get_user_model()

def finance_summary_totals():
    """
    Returns totals used by finance dashboard cards:
    - committed_total (FF3)
    - paid_total (FF4 / Treasury)
    - remaining_total
    - paid_percent
    """

    committed_total = (
        Payment.objects
        .filter(status=Payment.STATUS_COMMITTED)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    paid_total = (
        Payment.objects
        .filter(status=Payment.STATUS_PAID)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    remaining_total = committed_total - paid_total

    paid_percent = (
        int((paid_total / committed_total) * 100)
        if committed_total > 0
        else 0
    )

    return {
        "committed_total": committed_total,
        "paid_total": paid_total,
        "remaining_total": remaining_total,
        "paid_percent": paid_percent,
    }

# ---------------- Utility permission checks ----------------

def is_provincial_admin(user):
    return user.is_superuser or user.groups.filter(name="Provincial Administrators").exists()


def is_section32_or_finance(user):
    return user.is_superuser or user.groups.filter(name__in=["Section32 Officers", "Finance Officers"]).exists()


# ---------------- FF4 / IFMS CSV export ----------------

@login_required
@user_passes_test(is_provincial_admin)
def export_ff4_report(request):
    response = HttpResponse(content_type="text/csv")
    filename = f"FF4_Report_{timezone.localdate().year}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(["Vendor Code", "Vendor Name", "Budget Vote", "Description", "Amount", "Treasury Release Date", "Batch Number"])

    paid_payments = Payment.objects.filter(status=Payment.STATUS_PAID).select_related("application__institution", "budget_vote", "application__applicant__user")

    for p in paid_payments:
        inst = getattr(p.application, "institution", None)

        # Prefer Institution vendor_code if you have it, else fallback to Payment.vendor_code
        vendor_code = getattr(inst, "vendor_code", None) or p.vendor_code or ""
        vendor_name = getattr(inst, "name", "") if inst else ""

        vote_code = p.budget_vote.vote_code if p.budget_vote else (p.vote_item_code or "")

        applicant_user = getattr(getattr(p.application, "applicant", None), "user", None)
        applicant_name = applicant_user.get_full_name() if applicant_user else f"Application {p.application.pk}"
        description = f"Scholarship for {applicant_name}"

        amount = f"{Decimal(p.amount):.2f}"
        treasury_date = p.treasury_release_date.strftime("%d/%m/%Y") if p.treasury_release_date else ""
        writer.writerow([vendor_code, vendor_name, vote_code, description, amount, treasury_date, p.batch_number or ""])

    return response


# ---------------- Payment status endpoints ----------------

@login_required
@user_passes_test(is_section32_or_finance)
@require_POST
def commit_payment(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    try:
        if payment.status == Payment.STATUS_CANCELLED:
            return JsonResponse({"error": "Cannot commit a cancelled payment."}, status=400)
        payment.commit(user=request.user)
        return JsonResponse({"status": "committed", "payment_id": payment.id})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


@login_required
@user_passes_test(is_section32_or_finance)
@require_POST
def mark_payment_paid(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    try:
        treasury_date_str = request.POST.get("treasury_date")
        batch_number = request.POST.get("batch_number")

        treasury_date = parse_date(treasury_date_str) if treasury_date_str else None
        payment.mark_paid(user=request.user, treasury_date=treasury_date, batch_number=batch_number)

        return JsonResponse({"status": "paid", "payment_id": payment.id})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


@login_required
@user_passes_test(is_section32_or_finance)
@require_POST
def cancel_payment(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    reason = request.POST.get("reason", "")
    try:
        payment.cancel(user=request.user, reason=reason)
        return JsonResponse({"status": "cancelled", "payment_id": payment.id})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)



# ---------------- PDF generation, listing, viewing, download, upload ----------------

@login_required
@user_passes_test(is_provincial_admin)
def download_generated_pdf(request, pk):
    """
    Download a previously generated PDF (served from storage).
    Provincial Admins only.
    """
    gen = get_object_or_404(GeneratedPDF, pk=pk)
    if not gen.file:
        raise Http404("File not available")
    PDFAudit.objects.create(user=request.user, action="DOWNLOADED", generated_pdf=gen)
    return FileResponse(gen.file.open("rb"), as_attachment=True, filename=os.path.basename(gen.file.name))


@login_required
@user_passes_test(is_provincial_admin)
@require_POST
def generate_pdf_for_payment(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    template = FillablePDFTemplate.objects.filter(template_type="FF4").first()
    if not template:
        return JsonResponse({"error": "FF4 template not configured"}, status=400)

    gen = GeneratedPDF.objects.create(template=template, payment=payment, generated_by=request.user, status="PENDING")

    applicant_user = getattr(getattr(payment.application, "applicant", None), "user", None)
    applicant_label = payment.application.applicant.user.get_full_name()

    field_map = {
        "payment_id": str(payment.id),
        "applicant_name": applicant_label,
        "institution_name": getattr(getattr(payment.application, "institution", None), "name", ""),
        "amount": f"{Decimal(payment.amount):.2f}",
        "payment_date": payment.payment_date.strftime("%d/%m/%Y") if payment.payment_date else timezone.localdate().strftime("%d/%m/%Y"),
        "budget_vote": payment.budget_vote.vote_code if payment.budget_vote else (payment.vote_item_code or ""),
        "vendor_code": payment.vendor_code or "",
        "cheque_number": payment.cheque_number or "",
        "batch_number": payment.batch_number or "",
        "form11_identifier": payment.form11_identifier or "",
        "section_32_officer": payment.section_32_officer or "",
    }

    api_key = getattr(settings, "TWO_PDF_API_KEY", None)
    api_url = getattr(settings, "TWO_PDF_API_URL", "https://api.2pdf.com/fill")

    try:
        payload = {"template_id": template.template_id, "fields": field_map, "flatten": True}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"} if api_key else {"Content-Type": "application/json"}
        resp = requests.post(api_url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")

        if "application/pdf" in content_type:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            tmp.write(resp.content)
            tmp.flush()
            tmp.close()

            with open(tmp.name, "rb") as f:
                gen.file.save(f"ff4_{payment.id}_{gen.id}.pdf", File(f), save=True)

            os.unlink(tmp.name)
            gen.status = "READY"
            gen.save(update_fields=["status", "file"])
            PDFAudit.objects.create(user=request.user, action="GENERATED", generated_pdf=gen, notes="Synchronous generation")
            return JsonResponse({"status": "ready", "download_url": gen.file.url})

        # else: service returns JSON pointing to a URL
        data = resp.json()
        file_url = data.get("file_url") or data.get("url")
        if not file_url:
            gen.status = "FAILED"
            gen.notes = "No file returned by PDF service"
            gen.save(update_fields=["status", "notes"])
            return JsonResponse({"error": "No file returned by PDF service"}, status=500)

        file_resp = requests.get(file_url, timeout=30)
        file_resp.raise_for_status()

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmp.write(file_resp.content)
        tmp.flush()
        tmp.close()

        with open(tmp.name, "rb") as f:
            gen.file.save(f"ff4_{payment.id}_{gen.id}.pdf", File(f), save=True)

        os.unlink(tmp.name)
        gen.status = "READY"
        gen.external_id = data.get("id", "")
        gen.save(update_fields=["status", "file", "external_id"])
        PDFAudit.objects.create(user=request.user, action="GENERATED", generated_pdf=gen, notes="Synchronous generation (URL)")
        return JsonResponse({"status": "ready", "download_url": gen.file.url})

    except Exception as exc:
        gen.status = "FAILED"
        gen.notes = str(exc)
        gen.save(update_fields=["status", "notes"])
        PDFAudit.objects.create(user=request.user, action="GENERATED", generated_pdf=gen, notes=f"Failed: {exc}")
        return JsonResponse({"error": str(exc)}, status=500)


@login_required
@user_passes_test(is_section32_or_finance)
def pdf_list(request):
    """List generated PDFs and queued items for Section 32 / Finance officers."""
    items = GeneratedPDF.objects.select_related("template", "payment").order_by("-generated_at")
    return render(request, "finance/pdf_list.html", {"items": items})


@login_required
@user_passes_test(is_section32_or_finance)
def trigger_generate_pdf(request, generated_pdf_id):
    """Queue a previously created GeneratedPDF for processing by the background worker."""
    gen = get_object_or_404(GeneratedPDF, pk=generated_pdf_id)
    if gen.status in ("PENDING", "FAILED"):
        process_generated_pdf.delay(gen.id)
        PDFAudit.objects.create(user=request.user, action="GENERATED", generated_pdf=gen, notes="Queued via trigger")
    return redirect("finance:pdf_list")


@login_required
@user_passes_test(is_section32_or_finance)
def pdf_view(request, pk):
    """Show embedded PDF viewer for the generated PDF. If file not ready show status."""
    gen = get_object_or_404(GeneratedPDF, pk=pk)
    PDFAudit.objects.create(user=request.user, action="VIEWED", generated_pdf=gen)
    if gen.status != "READY" or not gen.file:
        return render(request, "finance/pdf_pending.html", {"gen": gen})
    return render(request, "finance/pdf_view.html", {"gen": gen})


@login_required
@user_passes_test(is_section32_or_finance)
def pdf_download(request, pk):
    gen = get_object_or_404(GeneratedPDF, pk=pk)
    if not gen.file:
        raise Http404("File not available")
    PDFAudit.objects.create(user=request.user, action="DOWNLOADED", generated_pdf=gen)
    filename = os.path.basename(gen.file.name)
    return FileResponse(gen.file.open("rb"), as_attachment=True, filename=filename)


@login_required
@user_passes_test(is_section32_or_finance)
@require_POST
def upload_signed_pdf(request, generated_pdf_id):
    gen = get_object_or_404(GeneratedPDF, pk=generated_pdf_id)
    uploaded_file = request.FILES.get("signed_pdf")
    if not uploaded_file:
        return JsonResponse({"error": "No file uploaded"}, status=400)
    signed = SignedPDF.objects.create(
        generated_pdf=gen,
        uploaded_by=request.user,
        file=uploaded_file,
        notes=request.POST.get("notes", ""),
    )
    PDFAudit.objects.create(user=request.user, action="SIGNED_UPLOADED", generated_pdf=gen, notes=f"SignedPDF id={signed.id}")
    return redirect("finance:pdf_view", pk=gen.id)


@login_required
@user_passes_test(is_section32_or_finance)
@require_POST
def save_edited_pdf(request, generated_pdf_id):
    gen = get_object_or_404(GeneratedPDF, pk=generated_pdf_id)
    edited = request.FILES.get("edited_pdf")
    if edited:
        signed = SignedPDF.objects.create(generated_pdf=gen, uploaded_by=request.user, file=edited, notes="Saved from PDF editor")
        PDFAudit.objects.create(user=request.user, action="SAVED_EDIT", generated_pdf=gen, notes=f"Saved edited PDF id={signed.id}")
        return JsonResponse({"status": "ok", "signed_id": signed.id})
    if request.content_type == "application/pdf":
        from django.core.files.base import ContentFile
        data = request.body
        filename = f"edited_{gen.id}.pdf"
        signed = SignedPDF.objects.create(generated_pdf=gen, uploaded_by=request.user)
        signed.file.save(filename, ContentFile(data))
        PDFAudit.objects.create(user=request.user, action="SAVED_EDIT", generated_pdf=gen, notes=f"Saved edited PDF id={signed.id}")
        return JsonResponse({"status": "ok", "signed_id": signed.id})
    return JsonResponse({"error": "No PDF provided"}, status=400)


# ---------------- Simple list/detail views for Payments and BudgetVotes ----------------

class PaymentListView(generic.ListView):
    model = Payment
    paginate_by = 50
    template_name = "finance/payment_list.html"
    context_object_name = "payments"
    queryset = Payment.objects.select_related("application", "budget_vote").order_by("-created_at")


class PaymentDetailView(generic.DetailView):
    model = Payment
    template_name = "finance/payment_detail.html"
    context_object_name = "payment"


class BudgetVoteListView(generic.ListView):
    model = BudgetVote
    paginate_by = 25
    template_name = "finance/budgetvote_list.html"
    context_object_name = "votes"
    queryset = BudgetVote.objects.order_by("-fiscal_year", "vote_code")


class BudgetVoteDetailView(generic.DetailView):
    model = BudgetVote
    template_name = "finance/budgetvote_detail.html"
    context_object_name = "vote"
