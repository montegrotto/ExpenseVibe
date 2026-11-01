from datetime import date
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image

from absence.models import AbsenceType, Period, TimeReport
from accounts.models import CustomUser
from api.models import ApiToken
from expenses.models import Category, Expense
from mileage.models import MileageRate, MileageReport


def _png():
    buffer = BytesIO()
    Image.new("RGB", (10, 10), "white").save(buffer, format="PNG")
    return SimpleUploadedFile("kvitto.png", buffer.getvalue(), content_type="image/png")


class ApiTests(TestCase):
    def setUp(self):
        self.employee = CustomUser.objects.create_user(
            email="anna@example.com", password="pw12345678", employment_number="1", must_change_password=False
        )
        self.approver = CustomUser.objects.create_user(
            email="bo@example.com", password="pw12345678", employment_number="2", must_change_password=False
        )
        self.approver.is_approver = True
        self.approver.save()
        self.category = Category.objects.create(name="Resor", code="RES")
        MileageRate.objects.create(amount_per_km="2.50", valid_from=date(2026, 1, 1))
        self.client = Client()

    def _auth(self, user):
        token = ApiToken.objects.create(user=user)
        return {"HTTP_AUTHORIZATION": f"Bearer {token.key}"}

    def test_login_returns_token_and_refuses_forced_password_change(self):
        response = self.client.post(
            reverse("api:login"),
            {"email": "anna@example.com", "password": "pw12345678"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ApiToken.objects.filter(key=response.json()["token"], user=self.employee).exists())

        self.employee.must_change_password = True
        self.employee.save()
        response = self.client.post(
            reverse("api:login"),
            {"email": "anna@example.com", "password": "pw12345678"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_missing_token_is_401(self):
        self.assertEqual(self.client.get(reverse("api:expenses")).status_code, 401)

    def test_upload_then_create_expense(self):
        auth = self._auth(self.employee)
        upload = self.client.post(reverse("api:attachment_upload"), {"file": _png()}, **auth)
        self.assertEqual(upload.status_code, 201)
        attachment_id = upload.json()["id"]

        bad = self.client.post(
            reverse("api:expenses"),
            {"attachment_id": attachment_id, "category": self.category.pk, "description": "Tåg"},
            content_type="application/json",
            **auth,
        )
        self.assertEqual(bad.status_code, 400)
        self.assertIn("amount", bad.json()["errors"])

        good = self.client.post(
            reverse("api:expenses"),
            {
                "attachment_id": attachment_id,
                "category": self.category.pk,
                "description": "Tåg",
                "expense_date": "2026-01-05",
                "amount": "123.00",
                "currency": "SEK",
            },
            content_type="application/json",
            **auth,
        )
        self.assertEqual(good.status_code, 201)
        expense = Expense.objects.get()
        self.assertEqual(expense.employee, self.employee)
        self.assertEqual(expense.status, "submitted")

        listed = self.client.get(reverse("api:expenses"), **auth).json()["results"]
        self.assertEqual([e["id"] for e in listed], [expense.pk])
        # Den anställde ser bara sina egna poster, även om listan är tom för någon annan.
        self.assertEqual(self.client.get(reverse("api:expenses"), **self._auth(self.approver)).json()["results"], [])
        # Attestanten får hämta kvittot, en annan anställd inte.
        self.assertEqual(
            self.client.get(
                reverse("api:attachment_file", args=[attachment_id]), **self._auth(self.approver)
            ).status_code,
            200,
        )

    def test_mileage_create_calculates_compensation(self):
        response = self.client.post(
            reverse("api:mileage"),
            {"date": "2026-02-01", "start_location": "A", "end_location": "B", "purpose": "Möte", "distance_km": "10"},
            content_type="application/json",
            **self._auth(self.employee),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["compensation_amount"], "25.00")
        self.assertEqual(MileageReport.objects.get().employee, self.employee)

    def test_approval_flow(self):
        report = MileageReport(
            employee=self.employee,
            date=date(2026, 2, 1),
            start_location="A",
            end_location="B",
            purpose="Möte",
            distance_km="10",
        )
        report.recalculate_compensation()
        report.save()

        self.assertEqual(self.client.get(reverse("api:approvals"), **self._auth(self.employee)).status_code, 403)
        auth = self._auth(self.approver)
        queue = self.client.get(reverse("api:approvals"), **auth).json()
        self.assertEqual([r["id"] for r in queue["mileage"]], [report.pk])

        rejected = self.client.post(
            reverse("api:reject", args=["kilometer", report.pk]), {}, content_type="application/json", **auth
        )
        self.assertEqual(rejected.status_code, 400)

        approved = self.client.post(reverse("api:approve", args=["kilometer", report.pk]), **auth)
        self.assertEqual(approved.status_code, 200)
        report.refresh_from_db()
        self.assertEqual(report.status, "approved")
        self.assertEqual(report.decided_by, self.approver)
        # Dubbelklick/kapplöpning: redan beslutad post ger 409, inte en ny ändring.
        self.assertEqual(
            self.client.post(reverse("api:approve", args=["kilometer", report.pk]), **auth).status_code, 409
        )

    def test_absence_report_submit_and_approve(self):
        sick = AbsenceType.objects.create(name="Sjuk", granularity=AbsenceType.Granularity.WHOLE_DAY)
        vab = AbsenceType.objects.create(name="VAB", granularity=AbsenceType.Granularity.HOURS)
        auth = self._auth(self.employee)
        url = reverse("api:absence")

        closed = self.client.get(url, {"month": "2026-10"}, **auth).json()
        self.assertFalse(closed["can_edit"])
        not_open = self.client.post(url, {"date": "2026-10-14", "absence_type": sick.pk}, content_type="application/json", **auth)
        self.assertIn("date", not_open.json()["errors"])

        Period.objects.create(month=date(2026, 10, 1))
        whole = self.client.post(url, {"date": "2026-10-14", "absence_type": sick.pk}, content_type="application/json", **auth)
        self.assertEqual(whole.status_code, 201)
        self.assertEqual(whole.json()["hours"], "8.00")
        # Modellvalideringen gäller som i webben: lördag är spärrad.
        weekend = self.client.post(
            url, {"date": "2026-10-17", "absence_type": vab.pk, "hours": "2"}, content_type="application/json", **auth
        )
        self.assertEqual(weekend.status_code, 400)
        extra = self.client.post(
            url, {"date": "2026-10-15", "absence_type": vab.pk, "hours": "2"}, content_type="application/json", **auth
        ).json()
        self.client.post(reverse("api:absence_delete", args=[extra["id"]]), **auth)

        month = self.client.get(url, {"month": "2026-10"}, **auth).json()
        self.assertTrue(month["can_edit"])
        self.assertEqual([e["absence_type"] for e in month["entries"]], ["Sjuk"])

        submit = reverse("api:absence_submit")
        self.assertEqual(self.client.post(submit, {"month": "2026-10"}, content_type="application/json", **auth).status_code, 200)
        report = TimeReport.objects.get(employee=self.employee)
        locked = self.client.post(reverse("api:absence_delete", args=[whole.json()["id"]]), **auth)
        self.assertEqual(locked.status_code, 409)

        approver = self._auth(self.approver)
        queue = self.client.get(reverse("api:approvals"), **approver).json()
        self.assertEqual([r["entries"][0]["date"] for r in queue["time_reports"]], ["2026-10-14"])
        self.client.post(reverse("api:approve", args=["tidrapport", report.pk]), **approver)
        report.refresh_from_db()
        self.assertEqual(report.status, "approved")

    def test_admin_password_reset_revokes_tokens(self):
        admin = CustomUser.objects.create_user(
            email="admin@example.com", password="pw12345678", employment_number="9", must_change_password=False
        )
        admin.is_admin = True
        admin.save()
        ApiToken.objects.create(user=self.employee)
        self.client.login(username="admin@example.com", password="pw12345678")
        self.client.post(
            reverse("accounts:user_set_password", args=[self.employee.pk]),
            {"password": "nyttpw123456", "password_confirm": "nyttpw123456"},
        )
        self.assertFalse(ApiToken.objects.filter(user=self.employee).exists())

    def test_qr_login_device_list_and_revoke(self):
        self.client.login(username="anna@example.com", password="pw12345678")
        response = self.client.post(reverse("accounts:mobile_app"))
        self.assertContains(response, "<svg")
        token = ApiToken.objects.get(user=self.employee, name="QR-kod")
        self.assertContains(response, f"token={token.key}")
        auth = {"HTTP_AUTHORIZATION": f"Bearer {token.key}"}
        self.assertEqual(self.client.get(reverse("api:me"), **auth).json()["user"]["email"], "anna@example.com")
        token.refresh_from_db()
        self.assertIsNotNone(token.last_used_at)

        # En kod som aldrig skannades i tid slutar fungera.
        stale = ApiToken.objects.create(user=self.employee)
        ApiToken.objects.filter(pk=stale.pk).update(created_at=stale.created_at - ApiToken.QR_LIFETIME * 2)
        self.assertEqual(self.client.get(reverse("api:me"), HTTP_AUTHORIZATION=f"Bearer {stale.key}").status_code, 401)
        self.assertFalse(ApiToken.objects.filter(pk=stale.pk).exists())

        # Enhetslistan: bara egna tokens kan återkallas.
        other = ApiToken.objects.create(user=self.approver)
        self.client.post(reverse("accounts:mobile_app"), {"revoke": other.pk})
        self.assertTrue(ApiToken.objects.filter(pk=other.pk).exists())
        self.assertContains(self.client.get(reverse("accounts:mobile_app")), "QR-kod")
        self.client.post(reverse("accounts:mobile_app"), {"revoke": token.pk})
        self.assertEqual(self.client.get(reverse("api:me"), **auth).status_code, 401)
