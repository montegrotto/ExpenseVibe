import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import urlencode
from qrcode.image.svg import SvgPathImage

from accounts.forms import (
    EmailAuthenticationForm,
    FirstAdminSignupForm,
    SetPasswordForm,
    StyledPasswordChangeForm,
    UserCreateForm,
    UserEditForm,
)
from accounts.models import CustomUser
from api.models import ApiToken
from core.decorators import admin_required


class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["no_users_yet"] = not CustomUser.objects.exists()
        return context


def first_admin_signup(request):
    """Bootstrap utan terminal: så länge systemet inte har en enda
    användare kan vem som helst som hittar hit skapa sig själv som
    administratör. Så fort en användare finns stängs vägen permanent - all
    fortsatt användarhantering sker via admins user_create ovan."""
    if CustomUser.objects.exists():
        raise Http404

    if request.method == "POST":
        form = FirstAdminSignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Administratörskontot är skapat.")
            return redirect("core:dashboard")
    else:
        form = FirstAdminSignupForm()
    return render(request, "accounts/first_admin_signup.html", {"form": form})


class ForcedPasswordChangeView(PasswordChangeView):
    template_name = "accounts/password_change.html"
    form_class = StyledPasswordChangeForm
    success_url = reverse_lazy("accounts:password_change_done")

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.user.must_change_password = False
        self.request.user.save(update_fields=["must_change_password"])
        return response


@login_required
def mobile_app(request):
    """Engångs-QR-kod som loggar in iPhone-appen (ios/) och användarens
    inloggade enheter med återkallning, som i SaldoVibe. Token visas bara i
    svaret på POST:en - en omladdning ger ingen ny kod."""
    tokens = request.user.api_tokens.all()
    revoke_id = request.POST.get("revoke", "")
    if revoke_id.isdigit():
        if tokens.filter(pk=int(revoke_id)).delete()[0]:
            messages.success(request, "Appinloggningen har återkallats.")
        return redirect("accounts:mobile_app")
    # Koder som aldrig skannades i tid gäller ändå inte längre.
    tokens.filter(last_used_at__isnull=True, created_at__lt=timezone.now() - ApiToken.QR_LIFETIME).delete()

    server_url = (settings.EXPENSEVIBE_PUBLIC_URL or request.build_absolute_uri("/")).rstrip("/")
    qr_svg = login_link = None
    if request.method == "POST":
        token = ApiToken.objects.create(user=request.user, name="QR-kod")
        login_link = f"expensevibe://login?{urlencode({'server': server_url, 'token': token.key})}"
        qr_svg = qrcode.make(login_link, image_factory=SvgPathImage, box_size=10, border=1).to_string(
            encoding="unicode"
        )
    return render(
        request,
        "accounts/mobile_app.html",
        {
            "server_url": server_url,
            "login_link": login_link,
            "qr_svg": qr_svg,
            "qr_lifetime_minutes": int(ApiToken.QR_LIFETIME.total_seconds() // 60),
            "tokens": tokens,
        },
    )


def password_change_done(request):
    messages.success(request, "Lösenordet är bytt.")
    return redirect("core:dashboard")


@admin_required
def user_list(request):
    users = CustomUser.objects.all()
    return render(request, "accounts/user_list.html", {"users": users})


@admin_required
def user_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Användaren är skapad.")
            return redirect("accounts:user_list")
    else:
        form = UserCreateForm()
    return render(request, "accounts/user_form.html", {"form": form, "title": "Ny användare"})


@admin_required
def user_edit(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    if request.method == "POST":
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Användaren är uppdaterad.")
            return redirect("accounts:user_list")
    else:
        form = UserEditForm(instance=user)
    return render(request, "accounts/user_form.html", {"form": form, "title": f"Redigera {user}"})


@admin_required
def user_set_password(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    if request.method == "POST":
        form = SetPasswordForm(request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data["password"])
            user.must_change_password = True
            user.save(update_fields=["password", "must_change_password"])
            # Logga ut alla telefoner (api.models.ApiToken) - det nya lösenordet
            # är satt av admin, inte av användaren själv.
            user.api_tokens.all().delete()
            messages.success(request, f"Nytt lösenord satt för {user}. Användaren tvingas byta det vid nästa inloggning.")
            return redirect("accounts:user_list")
    else:
        form = SetPasswordForm()
    return render(request, "accounts/user_set_password.html", {"form": form, "target_user": user})
