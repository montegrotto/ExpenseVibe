from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser


class CustomUserManagerTests(TestCase):
    def test_create_user_requires_email(self):
        with self.assertRaises(ValueError):
            CustomUser.objects.create_user(email="", password="x", employment_number="1")

    def test_create_superuser_sets_admin_flag(self):
        user = CustomUser.objects.create_superuser(email="admin@example.com", password="pw12345", employment_number="1")
        self.assertTrue(user.is_admin)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)


class FirstAdminSignupTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_signup_form_reachable_when_no_users_exist(self):
        response = self.client.get(reverse("accounts:first_admin_signup"))
        self.assertEqual(response.status_code, 200)

    def test_login_page_shows_signup_link_when_no_users_exist(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, reverse("accounts:first_admin_signup"))

    def test_signup_creates_admin_and_logs_in(self):
        response = self.client.post(
            reverse("accounts:first_admin_signup"),
            {
                "email": "forste@example.com",
                "first_name": "Förste",
                "last_name": "Admin",
                "employment_number": "1",
                "password": "ettbralosenord1",
                "password_confirm": "ettbralosenord1",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = CustomUser.objects.get(email="forste@example.com")
        self.assertTrue(user.is_admin)
        self.assertTrue(user.is_superuser)
        self.assertFalse(user.must_change_password)
        # Formuläret loggar in direkt - dashboarden ska vara nåbar utan ny inloggning.
        dashboard_response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(dashboard_response.status_code, 200)

    def test_mismatched_passwords_rejected(self):
        response = self.client.post(
            reverse("accounts:first_admin_signup"),
            {
                "email": "forste@example.com",
                "first_name": "Förste",
                "last_name": "Admin",
                "employment_number": "1",
                "password": "ettbralosenord1",
                "password_confirm": "nagotannat1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CustomUser.objects.exists())

    def test_signup_closed_once_a_user_exists(self):
        CustomUser.objects.create_user(email="finns@example.com", password="pw12345678", employment_number="1")

        get_response = self.client.get(reverse("accounts:first_admin_signup"))
        self.assertEqual(get_response.status_code, 404)

        login_response = self.client.get(reverse("accounts:login"))
        self.assertNotContains(login_response, reverse("accounts:first_admin_signup"))


class ForcedPasswordChangeTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="anna@example.com", password="startpw123", employment_number="42"
        )
        self.user.must_change_password = True
        self.user.save()
        self.client = Client()

    def test_login_redirects_to_forced_password_change(self):
        self.client.login(username="anna@example.com", password="startpw123")
        response = self.client.get(reverse("core:dashboard"))
        self.assertRedirects(response, reverse("accounts:password_change"))

    def test_changing_password_clears_flag(self):
        self.client.login(username="anna@example.com", password="startpw123")
        response = self.client.post(
            reverse("accounts:password_change"),
            {"old_password": "startpw123", "new_password1": "nyttlosenord123", "new_password2": "nyttlosenord123"},
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
        dashboard_response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(dashboard_response.status_code, 200)


class AdminUserManagementTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            email="admin@example.com", password="pw12345678", employment_number="1", is_admin=True
        )
        self.admin.must_change_password = False
        self.admin.save()
        self.employee = CustomUser.objects.create_user(
            email="employee@example.com", password="pw12345678", employment_number="2"
        )
        self.employee.must_change_password = False
        self.employee.save()
        self.client = Client()

    def test_non_admin_cannot_reach_user_list(self):
        self.client.login(username="employee@example.com", password="pw12345678")
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_create_user(self):
        self.client.login(username="admin@example.com", password="pw12345678")
        response = self.client.post(
            reverse("accounts:user_create"),
            {
                "email": "ny@example.com",
                "first_name": "Ny",
                "last_name": "Anställd",
                "employment_number": "99",
                "personal_identity_number": "",
                "password": "helttillfalligt1",
            },
        )
        self.assertEqual(response.status_code, 302)
        created = CustomUser.objects.get(email="ny@example.com")
        self.assertTrue(created.must_change_password)

    def test_admin_set_password_forces_change(self):
        self.client.login(username="admin@example.com", password="pw12345678")
        self.client.post(reverse("accounts:user_set_password", args=[self.employee.pk]), {"password": "annatlosenord1"})
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.must_change_password)
        self.assertTrue(self.employee.check_password("annatlosenord1"))


class LastAdminGuardTests(TestCase):
    """Regressionstest: den sista aktiva administratören får inte kunna
    avadministrera eller inaktivera sig själv - first_admin_signup är
    stängd så fort användare finns, så det skulle låsa ute alla admins."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            email="admin@example.com", password="pw12345678", employment_number="1", is_admin=True
        )
        self.admin.must_change_password = False
        self.admin.save()
        self.client = Client()
        self.client.login(username="admin@example.com", password="pw12345678")

    def _edit_payload(self, **overrides):
        payload = {
            "email": "admin@example.com",
            "first_name": "",
            "last_name": "",
            "employment_number": "1",
            "personal_identity_number": "",
            "is_active": "on",
        }
        payload.update(overrides)
        return payload

    def test_last_admin_cannot_remove_own_admin_flag(self):
        response = self.client.post(
            reverse("accounts:user_edit", args=[self.admin.pk]), self._edit_payload()
        )
        self.assertEqual(response.status_code, 200)  # formulärfel, ingen redirect
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_admin)

    def test_last_admin_cannot_deactivate_self(self):
        payload = self._edit_payload(is_admin="on")
        del payload["is_active"]
        response = self.client.post(reverse("accounts:user_edit", args=[self.admin.pk]), payload)
        self.assertEqual(response.status_code, 200)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_admin_can_be_demoted_when_another_active_admin_exists(self):
        CustomUser.objects.create_user(
            email="admin2@example.com", password="pw12345678", employment_number="2", is_admin=True
        )
        response = self.client.post(
            reverse("accounts:user_edit", args=[self.admin.pk]), self._edit_payload()
        )
        self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_admin)


class PasswordPolicyTests(TestCase):
    """Regressionstest: AUTH_PASSWORD_VALIDATORS ska gälla i alla
    lösenordsformulär, inte bara i Djangos inbyggda PasswordChangeForm."""

    def test_user_create_form_rejects_numeric_password(self):
        from accounts.forms import UserCreateForm

        form = UserCreateForm(
            {
                "email": "ny@example.com",
                "first_name": "",
                "last_name": "",
                "employment_number": "9",
                "personal_identity_number": "",
                "password": "12345678",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)

    def test_set_password_form_rejects_common_password(self):
        from accounts.forms import SetPasswordForm

        form = SetPasswordForm({"password": "password"})
        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)

    def test_first_admin_signup_form_rejects_common_password(self):
        from accounts.forms import FirstAdminSignupForm

        form = FirstAdminSignupForm(
            {
                "email": "boss@example.com",
                "first_name": "",
                "last_name": "",
                "employment_number": "1",
                "password": "password",
                "password_confirm": "password",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)
