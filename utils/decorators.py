# utils/decorators.py
from functools import wraps
from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings


def require_password_setup(view_func):
    """
    Redirect users who authenticated via SSO (no usable password)
    to the password setup page.

    - Skips staff & superusers
    - Safe for anonymous users
    """

    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        user = request.user

        if not user.is_authenticated:
            return view_func(request, *args, **kwargs)

        # Never block admins / staff
        if user.is_staff or user.is_superuser:
            return view_func(request, *args, **kwargs)

        if not user.has_usable_password():
            # configurable fallback
            url_name = getattr(settings, "PASSWORD_SETUP_URL", "applications:set_password")
            try:
                return redirect(reverse(url_name))
            except Exception:
                # hard fallback if route is missing
                return redirect("/accounts/password/set/")

        return view_func(request, *args, **kwargs)

    return _wrapped_view
