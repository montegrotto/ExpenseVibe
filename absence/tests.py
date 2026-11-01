from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from absence.holidays import is_non_working_day, non_working_day_name, swedish_holiday_name, swedish_public_holidays
from absence.models import AbsenceEntry, AbsenceSettings, AbsenceType, Period, TimeReport, WorkSchedule
from absence.services import open_period
from accounts.models import CustomUser


def _make_employee(email="anna@example.com", employment_number="1"):
    user = CustomUser.objects.create_user(email=email, password="pw12345678", employment_number=employment_number)
    user.must_change_password = False
    user.save()
    return user


def _make_admin(email="admin@example.com", employment_number="99"):
    user = CustomUser.objects.create_user(
        email=email, password="pw12345678", employment_number=employment_number, is_admin=True, is_approver=True
    )
    user.must_change_password = False
    user.save()
    return user


class SwedishHolidaysTests(TestCase):
    def test_2026_fixed_and_movable_holidays(self):
        holidays = swedish_public_holidays(2026)
        expected = {
            date(2026, 1, 1): "Nyårsdagen",
            date(2026, 1, 6): "Trettondedag jul",
            date(2026, 4, 3): "Långfredagen",
            date(2026, 4, 5): "Påskdagen",
            date(2026, 4, 6): "Annandag påsk",
            date(2026, 5, 1): "Första maj",
            date(2026, 5, 14): "Kristi himmelsfärdsdag",
            date(2026, 5, 24): "Pingstdagen",
            date(2026, 6, 6): "Sveriges nationaldag",
            date(2026, 6, 20): "Midsommardagen",
            date(2026, 10, 31): "Alla helgons dag",
            date(2026, 12, 25): "Juldagen",
            date(2026, 12, 26): "Annandag jul",
        }
        self.assertEqual(holidays, expected)

    def test_midsommardagen_and_alla_helgons_dag_always_saturday(self):
        for year in range(2024, 2031):
            holidays = swedish_public_holidays(year)
            midsommar = next(d for d, name in holidays.items() if name == "Midsommardagen")
            alla_helgon = next(d for d, name in holidays.items() if name == "Alla helgons dag")
            self.assertEqual(midsommar.weekday(), 5)
            self.assertEqual(alla_helgon.weekday(), 5)

    def test_swedish_holiday_name_returns_none_for_ordinary_day(self):
        self.assertIsNone(swedish_holiday_name(date(2026, 3, 10)))

    def test_swedish_holiday_name_returns_name_for_holiday(self):
        self.assertEqual(swedish_holiday_name(date(2026, 12, 25)), "Juldagen")

    def test_is_non_working_day_true_for_statutory_holiday_on_a_weekday(self):
        self.assertTrue(is_non_working_day(date(2026, 1, 6)))  # trettondedag jul, tisdag

    def test_is_non_working_day_true_for_julafton_and_nyarsafton(self):
        self.assertTrue(is_non_working_day(date(2026, 12, 24)))
        self.assertTrue(is_non_working_day(date(2026, 12, 31)))

    def test_is_non_working_day_true_for_midsommarafton(self):
        # Midsommardagen 2026 är lördagen 2026-06-20, alltså är
        # midsommarafton fredagen 2026-06-19.
        self.assertTrue(is_non_working_day(date(2026, 6, 19)))

    def test_midsommarafton_moves_with_midsommardagen(self):
        for year, expected in ((2025, date(2025, 6, 20)), (2027, date(2027, 6, 25)), (2028, date(2028, 6, 23))):
            self.assertEqual(non_working_day_name(expected), "Midsommarafton")

    def test_is_non_working_day_false_for_ordinary_weekday(self):
        self.assertFalse(is_non_working_day(date(2026, 3, 10)))  # tisdag, ingen helgdag


class AbsenceSettingsBlockingTests(TestCase):
    def test_weekend_blocked_by_default(self):
        settings_obj = AbsenceSettings.get_solo()
        self.assertTrue(settings_obj.blocks_date(date(2026, 3, 7)))  # lördag
        self.assertTrue(settings_obj.blocks_date(date(2026, 3, 8)))  # söndag

    def test_weekday_not_blocked_by_default(self):
        settings_obj = AbsenceSettings.get_solo()
        self.assertFalse(settings_obj.blocks_date(date(2026, 3, 9)))  # måndag

    def test_holiday_on_weekday_blocked_by_default(self):
        settings_obj = AbsenceSettings.get_solo()
        self.assertTrue(settings_obj.blocks_date(date(2026, 1, 6)))  # trettondedag jul, tisdag

    def test_julafton_nyarsafton_and_midsommarafton_blocked_by_default(self):
        settings_obj = AbsenceSettings.get_solo()
        self.assertTrue(settings_obj.blocks_date(date(2026, 12, 24)))  # julafton, torsdag
        self.assertTrue(settings_obj.blocks_date(date(2026, 12, 31)))  # nyårsafton, torsdag
        self.assertTrue(settings_obj.blocks_date(date(2026, 6, 19)))  # midsommarafton, fredag

    def test_nothing_blocked_when_setting_disabled(self):
        settings_obj = AbsenceSettings.get_solo()
        settings_obj.block_weekends_and_holidays = False
        settings_obj.save()
        self.assertFalse(settings_obj.blocks_date(date(2026, 3, 7)))
        self.assertFalse(settings_obj.blocks_date(date(2026, 1, 6)))
        self.assertFalse(settings_obj.blocks_date(date(2026, 12, 24)))


class WorkScheduleTests(TestCase):
    def test_get_for_employee_creates_default_mon_fri_schedule(self):
        employee = _make_employee()
        schedule = WorkSchedule.get_for_employee(employee)
        self.assertEqual(schedule.monday_hours, Decimal("8.00"))
        self.assertEqual(schedule.friday_hours, Decimal("8.00"))
        self.assertEqual(schedule.saturday_hours, Decimal("0.00"))
        self.assertEqual(schedule.sunday_hours, Decimal("0.00"))

    def test_get_for_employee_is_idempotent(self):
        employee = _make_employee()
        first = WorkSchedule.get_for_employee(employee)
        first.monday_hours = Decimal("4.00")
        first.save()
        second = WorkSchedule.get_for_employee(employee)
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(second.monday_hours, Decimal("4.00"))

    def test_hours_for_date_matches_weekday(self):
        employee = _make_employee()
        schedule = WorkSchedule.get_for_employee(employee)
        schedule.friday_hours = Decimal("6.00")
        schedule.save()
        self.assertEqual(schedule.hours_for_date(date(2026, 3, 5)), Decimal("8.00"))  # torsdag
        self.assertEqual(schedule.hours_for_date(date(2026, 3, 6)), Decimal("6.00"))  # fredag
        self.assertEqual(schedule.hours_for_date(date(2026, 3, 7)), Decimal("0.00"))  # lördag


class WorkScheduleViewTests(TestCase):
    def setUp(self):
        self.admin = _make_admin()
        self.employee = _make_employee()
        self.client = Client()
        self.client.login(username="admin@example.com", password="pw12345678")

    def test_list_requires_admin(self):
        other_client = Client()
        other_client.login(username="anna@example.com", password="pw12345678")
        response = other_client.get(reverse("absence:workschedule_list"))
        self.assertEqual(response.status_code, 403)

    def test_list_shows_employee(self):
        response = self.client.get(reverse("absence:workschedule_list"))
        self.assertContains(response, self.employee.email)

    def test_edit_creates_and_updates_schedule(self):
        response = self.client.post(
            reverse("absence:workschedule_edit", args=[self.employee.pk]),
            {
                "monday_hours": "4.00", "tuesday_hours": "4.00", "wednesday_hours": "4.00",
                "thursday_hours": "0.00", "friday_hours": "0.00", "saturday_hours": "0.00", "sunday_hours": "0.00",
            },
        )
        self.assertEqual(response.status_code, 302)
        schedule = WorkSchedule.objects.get(employee=self.employee)
        self.assertEqual(schedule.monday_hours, Decimal("4.00"))
        self.assertEqual(schedule.thursday_hours, Decimal("0.00"))


class PeriodTests(TestCase):
    def test_month_is_forced_to_day_one(self):
        period = Period.objects.create(month=date(2026, 3, 15))
        self.assertEqual(period.month, date(2026, 3, 1))

    def test_month_end(self):
        period = Period.objects.create(month=date(2026, 2, 1))
        self.assertEqual(period.month_end, date(2026, 2, 28))

    def test_is_reportable_for_without_time_report(self):
        employee = _make_employee()
        period = Period.objects.create(month=date(2026, 3, 1))
        self.assertTrue(period.is_reportable_for(employee))

    def test_is_reportable_for_blocked_when_submitted(self):
        employee = _make_employee()
        period = Period.objects.create(month=date(2026, 3, 1))
        TimeReport.objects.create(employee=employee, period=period)
        self.assertFalse(period.is_reportable_for(employee))

    def test_is_reportable_for_open_again_when_rejected(self):
        employee = _make_employee()
        admin = _make_admin()
        period = Period.objects.create(month=date(2026, 3, 1))
        report = TimeReport.objects.create(employee=employee, period=period)
        report.reject(admin, "Fel datum")
        self.assertTrue(period.is_reportable_for(employee))

    def test_is_reportable_for_blocked_when_not_open(self):
        employee = _make_employee()
        period = Period.objects.create(month=date(2026, 3, 1), status=Period.PeriodStatus.REPORTED)
        self.assertFalse(period.is_reportable_for(employee))


class AbsenceEntryValidationTests(TestCase):
    def setUp(self):
        self.employee = _make_employee()
        self.period = Period.objects.create(month=date(2026, 3, 1))
        self.sick = AbsenceType.objects.create(name="Sjukdom", export_code="801", granularity=AbsenceType.Granularity.HOURS)
        self.vacation = AbsenceType.objects.create(
            name="Semester", export_code="802", granularity=AbsenceType.Granularity.WHOLE_DAY
        )

    def _entry(self, **kwargs):
        defaults = {"employee": self.employee, "period": self.period, "date": date(2026, 3, 5)}
        defaults.update(kwargs)
        return AbsenceEntry(**defaults)

    def test_hours_required_for_hour_based_type(self):
        entry = self._entry(absence_type=self.sick, hours=None)
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_hours_must_be_empty_for_whole_day_type(self):
        entry = self._entry(absence_type=self.vacation, hours=Decimal("2.00"))
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_whole_day_snapshot_set_on_save(self):
        entry = self._entry(absence_type=self.vacation)
        entry.full_clean()
        entry.save()
        self.assertEqual(entry.workday_hours_snapshot, Decimal("8.00"))
        self.assertEqual(entry.effective_hours, Decimal("8.00"))

    def test_whole_day_snapshot_survives_later_schedule_change(self):
        entry = self._entry(absence_type=self.vacation)  # 2026-03-05 är en torsdag
        entry.full_clean()
        entry.save()

        schedule = WorkSchedule.get_for_employee(self.employee)
        schedule.thursday_hours = Decimal("6.00")
        schedule.save()

        entry.refresh_from_db()
        self.assertEqual(entry.workday_hours_snapshot, Decimal("8.00"))

    def test_whole_day_snapshot_uses_employees_own_weekday_hours(self):
        schedule = WorkSchedule.get_for_employee(self.employee)
        schedule.thursday_hours = Decimal("4.00")
        schedule.save()

        entry = self._entry(absence_type=self.vacation)  # 2026-03-05 är en torsdag
        entry.full_clean()
        entry.save()
        self.assertEqual(entry.workday_hours_snapshot, Decimal("4.00"))

    def test_date_must_be_within_period(self):
        entry = self._entry(absence_type=self.sick, hours=Decimal("2.00"), date=date(2026, 4, 1))
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_multiple_hour_entries_same_day_allowed_under_cap(self):
        self._entry(absence_type=self.sick, hours=Decimal("4.00")).save()
        second = self._entry(absence_type=self.sick, hours=Decimal("4.00"))
        second.full_clean()
        second.save()
        self.assertEqual(AbsenceEntry.objects.filter(date=date(2026, 3, 5)).count(), 2)

    def test_hour_entries_same_day_over_cap_rejected(self):
        self._entry(absence_type=self.sick, hours=Decimal("6.00")).save()
        second = self._entry(absence_type=self.sick, hours=Decimal("3.00"))
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_editing_existing_entry_excludes_itself_from_cap(self):
        entry = self._entry(absence_type=self.sick, hours=Decimal("4.00"))
        entry.save()
        entry.hours = Decimal("7.00")
        entry.full_clean()  # ska inte räkna med sig själv och därmed falskt överstiga taket

    def test_whole_day_exclusive_against_other_entries_same_day(self):
        self._entry(absence_type=self.vacation).save()
        other = self._entry(absence_type=self.sick, hours=Decimal("2.00"))
        with self.assertRaises(ValidationError):
            other.full_clean()

    def test_other_entry_blocked_when_whole_day_already_present(self):
        self._entry(absence_type=self.sick, hours=Decimal("2.00")).save()
        whole_day = self._entry(absence_type=self.vacation)
        with self.assertRaises(ValidationError):
            whole_day.full_clean()

    def test_blocked_when_period_not_open(self):
        self.period.status = Period.PeriodStatus.REPORTED
        self.period.save()
        entry = self._entry(absence_type=self.sick, hours=Decimal("2.00"))
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_blocked_while_time_report_submitted(self):
        TimeReport.objects.create(employee=self.employee, period=self.period)
        entry = self._entry(absence_type=self.sick, hours=Decimal("2.00"))
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_weekend_date_blocked_by_default(self):
        entry = self._entry(absence_type=self.sick, hours=Decimal("2.00"), date=date(2026, 3, 7))  # lördag
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_weekend_date_allowed_when_blocking_disabled(self):
        settings_obj = AbsenceSettings.get_solo()
        settings_obj.block_weekends_and_holidays = False
        settings_obj.save()
        # Schemat måste tillåta timmarna oberoende av helgblockeringen -
        # annars stoppar dagtaket (0h lördag som standard) ändå.
        schedule = WorkSchedule.get_for_employee(self.employee)
        schedule.saturday_hours = Decimal("4.00")
        schedule.save()
        entry = self._entry(absence_type=self.sick, hours=Decimal("2.00"), date=date(2026, 3, 7))
        entry.full_clean()  # ska inte höja ValidationError

    def test_inactive_type_blocked_for_new_entry(self):
        self.sick.is_active = False
        self.sick.save()
        entry = self._entry(absence_type=self.sick, hours=Decimal("2.00"))
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_inactive_type_does_not_block_editing_existing_entry(self):
        entry = self._entry(absence_type=self.sick, hours=Decimal("2.00"))
        entry.save()
        self.sick.is_active = False
        self.sick.save()
        entry.hours = Decimal("3.00")
        entry.full_clean()


class AbsenceCalendarViewTests(TestCase):
    def setUp(self):
        self.employee = _make_employee()
        self.other_employee = _make_employee(email="bertil@example.com", employment_number="2")
        self.period = Period.objects.create(month=date(2026, 3, 1))
        self.sick = AbsenceType.objects.create(name="Sjukdom", export_code="801", granularity=AbsenceType.Granularity.HOURS)
        self.client = Client()
        self.client.login(username="anna@example.com", password="pw12345678")

    def test_calendar_renders_for_open_period(self):
        response = self.client.get(reverse("absence:absence_calendar"), {"month": "2026-03"})
        self.assertEqual(response.status_code, 200)

    def test_create_entry(self):
        response = self.client.post(
            reverse("absence:absenceentry_create"),
            {"date": "2026-03-05", "absence_type": self.sick.pk, "hours": "4.00"},
        )
        self.assertEqual(response.status_code, 302)
        entry = AbsenceEntry.objects.get()
        self.assertEqual(entry.employee, self.employee)
        self.assertEqual(entry.period, self.period)

    def test_create_entry_without_open_period_shows_error(self):
        response = self.client.post(
            reverse("absence:absenceentry_create"),
            {"date": "2026-04-05", "absence_type": self.sick.pk, "hours": "4.00"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "inte öppnad")
        self.assertEqual(AbsenceEntry.objects.count(), 0)

    def test_cannot_edit_another_employees_entry(self):
        entry = AbsenceEntry.objects.create(
            employee=self.other_employee, period=self.period, date=date(2026, 3, 5), absence_type=self.sick,
            hours=Decimal("2.00"),
        )
        response = self.client.get(reverse("absence:absenceentry_edit", args=[entry.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_delete_another_employees_entry(self):
        entry = AbsenceEntry.objects.create(
            employee=self.other_employee, period=self.period, date=date(2026, 3, 5), absence_type=self.sick,
            hours=Decimal("2.00"),
        )
        response = self.client.post(reverse("absence:absenceentry_delete", args=[entry.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(AbsenceEntry.objects.filter(pk=entry.pk).exists())

    def test_delete_own_entry(self):
        entry = AbsenceEntry.objects.create(
            employee=self.employee, period=self.period, date=date(2026, 3, 5), absence_type=self.sick,
            hours=Decimal("2.00"),
        )
        response = self.client.post(reverse("absence:absenceentry_delete", args=[entry.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(AbsenceEntry.objects.filter(pk=entry.pk).exists())


class TimeReportFlowTests(TestCase):
    def setUp(self):
        self.employee = _make_employee()
        self.admin = _make_admin()
        self.period = Period.objects.create(month=date(2026, 3, 1))
        self.sick = AbsenceType.objects.create(name="Sjukdom", export_code="801", granularity=AbsenceType.Granularity.HOURS)
        AbsenceEntry.objects.create(
            employee=self.employee, period=self.period, date=date(2026, 3, 5), absence_type=self.sick,
            hours=Decimal("4.00"),
        )
        self.client = Client()
        self.client.login(username="anna@example.com", password="pw12345678")

    def test_mark_done_creates_submitted_time_report(self):
        response = self.client.post(reverse("absence:timereport_submit"), {"month": "2026-03"})
        self.assertEqual(response.status_code, 302)
        report = TimeReport.objects.get()
        self.assertEqual(report.status, "submitted")
        self.assertEqual(report.employee, self.employee)

    def test_new_entry_blocked_after_mark_done(self):
        self.client.post(reverse("absence:timereport_submit"), {"month": "2026-03"})
        response = self.client.post(
            reverse("absence:absenceentry_create"),
            {"date": "2026-03-10", "absence_type": self.sick.pk, "hours": "2.00"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AbsenceEntry.objects.count(), 1)

    def test_reject_then_edit_then_resubmit(self):
        self.client.post(reverse("absence:timereport_submit"), {"month": "2026-03"})
        report = TimeReport.objects.get()
        report.reject(self.admin, "Fel timmar")

        entry = AbsenceEntry.objects.get()
        edit_response = self.client.post(
            reverse("absence:absenceentry_edit", args=[entry.pk]),
            {"date": "2026-03-05", "absence_type": self.sick.pk, "hours": "3.00"},
        )
        self.assertEqual(edit_response.status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.hours, Decimal("3.00"))

        resubmit_response = self.client.post(reverse("absence:timereport_submit"), {"month": "2026-03"})
        self.assertEqual(resubmit_response.status_code, 302)
        report.refresh_from_db()
        self.assertEqual(report.status, "submitted")

    def test_approval_queue_lists_submitted_time_report(self):
        self.client.post(reverse("absence:timereport_submit"), {"month": "2026-03"})
        report = TimeReport.objects.get()

        approver_client = Client()
        approver_client.login(username="admin@example.com", password="pw12345678")
        response = approver_client.get(reverse("core:approval_queue"))
        self.assertContains(response, str(report.period))

        approve_response = approver_client.post(reverse("core:approve_item", args=["tidrapport", report.pk]))
        self.assertEqual(approve_response.status_code, 302)
        report.refresh_from_db()
        self.assertEqual(report.status, "approved")


class OpenPeriodCommandTests(TestCase):
    def test_creates_and_opens_period_for_given_month(self):
        out = StringIO()
        call_command("open_period", "--month", "2026-05", stdout=out)
        period = Period.objects.get(month=date(2026, 5, 1))
        self.assertEqual(period.status, Period.PeriodStatus.OPEN)
        self.assertIn("öppnad", out.getvalue())

    def test_idempotent_second_run(self):
        call_command("open_period", "--month", "2026-05")
        out = StringIO()
        call_command("open_period", "--month", "2026-05", stdout=out)
        self.assertEqual(Period.objects.filter(month=date(2026, 5, 1)).count(), 1)
        self.assertIn("fanns redan", out.getvalue())

    def test_open_period_service_used_by_command_is_idempotent(self):
        _, created_first = open_period(date(2026, 6, 1))
        _, created_second = open_period(date(2026, 6, 1))
        self.assertTrue(created_first)
        self.assertFalse(created_second)


class WholeDaySnapshotRecalcTests(TestCase):
    """Regressionstest: flyttas en Hel dag-post till en annan veckodag ska
    workday_hours_snapshot räknas om mot det nya datumets schemalagda
    timmar, inte behålla den gamla veckodagens värde."""

    def test_snapshot_recalculated_when_date_changes(self):
        employee = CustomUser.objects.create_user(
            email="anna@example.com", password="pw12345678", employment_number="1"
        )
        schedule = WorkSchedule.get_for_employee(employee)
        schedule.friday_hours = Decimal("4.00")
        schedule.save()
        Period.objects.create(month=date(2026, 3, 1))
        vacation = AbsenceType.objects.create(
            name="Semester", export_code="802", granularity=AbsenceType.Granularity.WHOLE_DAY
        )
        entry = AbsenceEntry(
            employee=employee,
            period=Period.objects.get(month=date(2026, 3, 1)),
            date=date(2026, 3, 2),  # måndag, 8h
            absence_type=vacation,
        )
        entry.full_clean()
        entry.save()
        self.assertEqual(entry.workday_hours_snapshot, Decimal("8.00"))

        entry.date = date(2026, 3, 6)  # fredag, 4h
        entry.full_clean()
        entry.save()
        entry.refresh_from_db()
        self.assertEqual(entry.workday_hours_snapshot, Decimal("4.00"))


class WorkScheduleBoundsTests(TestCase):
    """Regressionstest: schematimmar måste ligga i intervallet 0-24 -
    negativa värden korrumperade tidigare frånvarodata och exporten."""

    def test_negative_and_absurd_hours_rejected(self):
        from absence.forms import WorkScheduleForm

        employee = CustomUser.objects.create_user(
            email="anna@example.com", password="pw12345678", employment_number="1"
        )
        schedule = WorkSchedule.get_for_employee(employee)
        form = WorkScheduleForm(
            {
                "monday_hours": "-5.00",
                "tuesday_hours": "30.00",
                "wednesday_hours": "8.00",
                "thursday_hours": "8.00",
                "friday_hours": "8.00",
                "saturday_hours": "0.00",
                "sunday_hours": "0.00",
            },
            instance=schedule,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("monday_hours", form.errors)
        self.assertIn("tuesday_hours", form.errors)
