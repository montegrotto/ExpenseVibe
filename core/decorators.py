from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def admin_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin:
            raise PermissionDenied("Kräver administratörsbehörighet.")
        return view_func(request, *args, **kwargs)

    return wrapper


def approver_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_approver:
            raise PermissionDenied("Kräver attestantbehörighet.")
        return view_func(request, *args, **kwargs)

    return wrapper
