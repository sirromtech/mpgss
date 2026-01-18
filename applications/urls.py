# applications/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from .views_media import secure_document, view_document
from . import views, views_review

app_name = "applications"

urlpatterns = [

    # ------------------------------------------------------------------
    # Public / Home
    # ------------------------------------------------------------------
    path("", views.home_view, name="home"),

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", views.logout_view, name="logout"),
    path("secure-media/<path:key>", secure_document, name="secure_document"),
    path("documents/<path:key>/", view_document, name="view_document"),


    # ------------------------------------------------------------------
    # Student Applications
    # ------------------------------------------------------------------
    path("apply/", views.choose_application_type, name="apply"),
    path("apply/new/", views.create_application, name="create_application"),
    path("apply/success/", views.application_success, name="application_success"),
 

    # Student dashboards
    path("dashboard/", views.user_dashboard, name="user_dashboard"),
    path("dashboard/continuing/", views.continuing_dashboard, name="continuing_dashboard"),

    # Continuing / Legacy
    path("legacy/lookup/", views.lookup_legacy, name="lookup_legacy"),
    path("legacy/confirm/", views.confirm_legacy, name="confirm_legacy"),

    # Entry point for continuing applicants (goes to legacy lookup form)
    path("apply/continuing/", views.lookup_legacy, name="apply_continuing"),

    # After confirming legacy student, continue application by pk
    path("continue/<int:pk>/", views.continue_application, name="continue_application"),
   

    # Edit continuing (one-time edit)
    path("applications/<int:pk>/edit/", views.edit_continuing_application, name="edit_continuing_application"),

    # API
    path("api/courses/", views.courses_api, name="courses_api"),

    # ------------------------------------------------------------------
    # OFFICERS
    # ------------------------------------------------------------------
    # Officer Dashboard (navbar landing)
    path("officer/dashboard/", views.officer_dashboard, name="officer_dashboard"),

    # Review list (filterable: ?type=new / ?type=continuing)
    path("officer/reviews/", views_review.review_list, name="review_list"),

    # Canonical: Officer application detail review page
    path("officer/application/<int:pk>/", views_review.review_application, name="officer_application_detail"),

    # Backward compatibility: old name used in templates
    # This makes {% url 'applications:review_application' app.pk %} work again.
    path("officer/application/<int:pk>/", views_review.review_application, name="review_application"),

    # Optional backward compatibility: old URL path "/officer/review/<pk>/"
    path("officer/review/<int:pk>/", views_review.review_application, name="officer_review_alias"),

    # Backward compatibility: profile view (if you still use it)
 

    # Officer: view student profile (read-only)
    path("officer/student/<int:pk>/", views.officer_view_student_profile, name="officer_view_student_profile"),

    # Officer export
    path("officer/export/", views.export_applications_csv, name="export_applications"),

    # ------------------------------------------------------------------
    # Password Reset
    # ------------------------------------------------------------------
    path("password-reset/", auth_views.PasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", auth_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),

    # ------------------------------------------------------------------
    # Static Pages
    # ------------------------------------------------------------------
    path("faq/", views.faq_view, name="faq"),
    path("terms/", views.terms_view, name="terms"),
    path("privacy/", views.privacy_view, name="privacy"),
    path("about/", views.about_view, name="about"),

    # ------------------------------------------------------------------
    # News
    # ------------------------------------------------------------------
    path("news_list/", views.news_list, name="news_list"),
    path("news/<int:pk>/", views.news_detail, name="news_detail"),

    # ------------------------------------------------------------------
    # AI / OCR Scanning
    # ------------------------------------------------------------------
    path("scanning/<str:task_id>/", views.scanning, name="scanning"),
    path("scan-progress/<str:task_id>/", views.scan_progress, name="scan_progress"),
    path("scan-result/<str:task_id>/", views.scan_result, name="scan_result"),
]
