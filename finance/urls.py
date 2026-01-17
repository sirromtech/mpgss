# finance/urls.py
from django.urls import path
from . import views

app_name = "finance"

urlpatterns = [
    # PDF listing / viewer
    path("pdfs/", views.pdf_list, name="pdf_list"),
    path("pdfs/view/<int:pk>/", views.pdf_view, name="pdf_view"),

    # Generate PDFs
    path("pdfs/generate/<int:payment_id>/", views.generate_pdf_for_payment, name="generate_pdf_for_payment"),
    path("pdfs/queue/<int:generated_pdf_id>/", views.trigger_generate_pdf, name="queue_generated_pdf"),

    # Downloads (separate by audience)
    path("pdfs/download/<int:pk>/", views.pdf_download, name="pdf_download"),  # Section32/Finance
    path("pdfs/admin-download/<int:pk>/", views.download_generated_pdf, name="admin_download_generated_pdf"),  # Provincial Admin

    # Upload / Save signed or edited
    path("pdfs/upload-signed/<int:generated_pdf_id>/", views.upload_signed_pdf, name="upload_signed_pdf"),
    path("pdfs/save-edited/<int:generated_pdf_id>/", views.save_edited_pdf, name="save_edited_pdf"),

    # FF4 / IFMS export
    path("export/ff4/", views.export_ff4_report, name="export_ff4_report"),

    # Payment status endpoints (POST)
    path("payments/<int:payment_id>/commit/", views.commit_payment, name="commit_payment"),
    path("payments/<int:payment_id>/mark-paid/", views.mark_payment_paid, name="mark_payment_paid"),
    path("payments/<int:payment_id>/cancel/", views.cancel_payment, name="cancel_payment"),

    # Payments list / detail
    path("payments/", views.PaymentListView.as_view(), name="payment_list"),
    path("payments/<int:pk>/", views.PaymentDetailView.as_view(), name="payment_detail"),

    # Budget votes list / detail
    path("votes/", views.BudgetVoteListView.as_view(), name="budgetvote_list"),
    path("votes/<int:pk>/", views.BudgetVoteDetailView.as_view(), name="budgetvote_detail"),
]
