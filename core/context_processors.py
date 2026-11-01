def nav_counts(request):
    """Antal väntande attesteringar för sidomenyns badge. Lokal import av
    expenses/mileage undviker en cirkulär import (de ärver core.Approvable)."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not user.is_approver:
        return {}

    from absence.models import TimeReport
    from expenses.models import Expense
    from mileage.models import MileageReport

    pending = (
        Expense.objects.filter(status="submitted").count()
        + MileageReport.objects.filter(status="submitted").count()
        + TimeReport.objects.filter(status="submitted").count()
    )
    return {"pending_approval_count": pending}
