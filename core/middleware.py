from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

# Vyer som måste vara nåbara även när ett lösenordsbyte är tvingat, annars
# kan användaren aldrig ta sig till bytesformuläret (eller logga ut).
_EXEMPT_URL_NAMES = {"accounts:password_change", "accounts:password_change_done", "accounts:logout"}


class ForcePasswordChangeMiddleware:
    """Tvingar ett lösenordsbyte innan resten av systemet är åtkomligt, när
    admin har (åter)satt en användares lösenord - se accounts.models.CustomUser.
    must_change_password och accounts/views.py."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and getattr(user, "must_change_password", False)
            and request.path not in self._exempt_paths()
            and not request.path.startswith("/static/")
            and not request.path.startswith("/media/")
        ):
            messages.info(request, "Du måste byta lösenord innan du kan fortsätta.")
            return redirect("accounts:password_change")
        return self.get_response(request)

    @staticmethod
    def _exempt_paths():
        paths = set()
        for name in _EXEMPT_URL_NAMES:
            try:
                paths.add(reverse(name))
            except Exception:
                continue
        return paths
