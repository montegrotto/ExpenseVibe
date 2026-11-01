from datetime import date
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser
from mileage.models import MileageRate, MileageReport


class MileageRateLookupTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            email="admin@example.com", password="pw12345678", employment_number="1", is_admin=True
        )
        MileageRate.objects.create(amount_per_km="25.00", export_code="050", valid_from=date(2025, 1, 1), created_by=self.admin)
        MileageRate.objects.create(amount_per_km="27.00", export_code="050", valid_from=date(2026, 1, 1), created_by=self.admin)

    def test_current_picks_latest_rate_not_in_the_future(self):
        self.assertEqual(MileageRate.current(on_date=date(2025, 6, 1)).amount_per_km, Decimal("25.00"))
        self.assertEqual(MileageRate.current(on_date=date(2026, 6, 1)).amount_per_km, Decimal("27.00"))

    def test_current_uses_trip_date_not_todays_rate(self):
        """En sent inlagd rapport för en äldre resa ska få den sats som
        gällde DÅ, inte dagens sats."""
        rate_for_old_trip = MileageRate.current(on_date=date(2025, 3, 15))
        self.assertEqual(rate_for_old_trip.amount_per_km, Decimal("25.00"))

    def test_no_rate_before_any_configured(self):
        self.assertIsNone(MileageRate.current(on_date=date(2020, 1, 1)))


class MileageReportCompensationTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            email="admin@example.com", password="pw12345678", employment_number="1", is_admin=True
        )
        self.rate = MileageRate.objects.create(
            amount_per_km="25.00", export_code="050", export_code_name="Bilersättning (km)", valid_from=date(2026, 1, 1),
            created_by=self.admin,
        )

    def test_recalculate_compensation_multiplies_distance_by_rate(self):
        report = MileageReport(
            employee=self.admin, date=date(2026, 2, 1), start_location="Kontoret", end_location="Kunden",
            purpose="Möte", distance_km="12.0",
        )
        self.assertTrue(report.recalculate_compensation())
        self.assertEqual(report.compensation_amount, Decimal("300.00"))
        self.assertEqual(report.mileage_rate, self.rate)


class MileageReportFlowTests(TestCase):
    def setUp(self):
        self.employee = CustomUser.objects.create_user(
            email="anna@example.com", password="pw12345678", employment_number="1"
        )
        self.employee.must_change_password = False
        self.employee.save()
        self.client = Client()
        self.client.login(username="anna@example.com", password="pw12345678")

    def test_submission_blocked_without_configured_rate(self):
        response = self.client.post(
            reverse("mileage:mileagereport_create"),
            {
                "date": "2026-03-01",
                "start_location": "Kontoret",
                "end_location": "Kunden",
                "purpose": "Möte",
                "distance_km": "10.0",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ingen km-sats är konfigurerad")
        self.assertEqual(MileageReport.objects.count(), 0)

    def test_submission_succeeds_with_configured_rate(self):
        MileageRate.objects.create(amount_per_km="25.00", export_code="050", valid_from=date(2026, 1, 1))
        response = self.client.post(
            reverse("mileage:mileagereport_create"),
            {
                "date": "2026-03-01",
                "start_location": "Kontoret",
                "end_location": "Kunden",
                "purpose": "Möte",
                "distance_km": "10.0",
            },
        )
        self.assertEqual(response.status_code, 302)
        report = MileageReport.objects.get()
        self.assertEqual(report.compensation_amount, Decimal("250.00"))
        self.assertEqual(report.status, "submitted")
