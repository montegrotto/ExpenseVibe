from datetime import date
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image

from accounts.models import CustomUser
from attachments.models import Attachment
from expenses.models import Category, Expense


def _fake_receipt_png():
    buffer = BytesIO()
    Image.new("RGB", (10, 10), "white").save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile("kvitto.png", buffer.read(), content_type="image/png")


class CategoryProtectionTests(TestCase):
    def setUp(self):
        self.employee = CustomUser.objects.create_user(
            email="anna@example.com", password="pw12345678", employment_number="1"
        )
        self.category = Category.objects.create(name="Resor", code="RES")

    def test_can_delete_unused_category(self):
        self.assertTrue(self.category.can_delete)

    def test_cannot_delete_category_with_expenses(self):
        attachment = Attachment.objects.create(file=_fake_receipt_png(), uploaded_by=self.employee)
        Expense.objects.create(
            employee=self.employee,
            attachment=attachment,
            category=self.category,
            description="Tågbiljett",
            expense_date=date(2026, 1, 5),
            amount="123.00",
        )
        self.assertFalse(self.category.can_delete)


class ExpenseUploadFlowTests(TestCase):
    def setUp(self):
        self.employee = CustomUser.objects.create_user(
            email="anna@example.com", password="pw12345678", employment_number="1"
        )
        self.employee.must_change_password = False
        self.employee.save()
        self.other = CustomUser.objects.create_user(
            email="bertil@example.com", password="pw12345678", employment_number="2"
        )
        self.other.must_change_password = False
        self.other.save()
        self.category = Category.objects.create(name="Resor", code="RES")
        self.client = Client()
        self.client.login(username="anna@example.com", password="pw12345678")

    def test_full_two_step_flow_creates_submitted_expense(self):
        upload_response = self.client.post(reverse("attachments:upload"), {"file": _fake_receipt_png()})
        self.assertEqual(upload_response.status_code, 302)
        attachment = Attachment.objects.get(uploaded_by=self.employee)
        self.assertTrue(attachment.content_hash)

        create_url = f"{reverse('expenses:expense_create')}?attachment_id={attachment.pk}"
        get_response = self.client.get(create_url)
        self.assertEqual(get_response.status_code, 200)

        post_response = self.client.post(
            create_url,
            {
                "category": self.category.pk,
                "description": "Taxi till kundmöte",
                "expense_date": "2026-02-01",
                "amount": "245.00",
                "currency": "SEK",
            },
        )
        self.assertEqual(post_response.status_code, 302)
        expense = Expense.objects.get(attachment=attachment)
        self.assertEqual(expense.status, "submitted")
        self.assertEqual(expense.employee, self.employee)

    def test_cannot_create_expense_from_someone_elses_attachment(self):
        attachment = Attachment.objects.create(file=_fake_receipt_png(), uploaded_by=self.other)
        response = self.client.get(f"{reverse('expenses:expense_create')}?attachment_id={attachment.pk}")
        self.assertEqual(response.status_code, 404)

    def test_employee_cannot_see_others_expense(self):
        attachment = Attachment.objects.create(file=_fake_receipt_png(), uploaded_by=self.other)
        expense = Expense.objects.create(
            employee=self.other,
            attachment=attachment,
            category=self.category,
            description="Hotell",
            expense_date=date(2026, 1, 5),
            amount="900.00",
        )
        response = self.client.get(reverse("expenses:expense_detail", args=[expense.pk]))
        self.assertEqual(response.status_code, 404)

    def test_self_attestation_is_allowed(self):
        """Uttryckligt beslut i planen: ingen jävsspärr - en attestant får
        attestera sina egna poster."""
        self.employee.is_approver = True
        self.employee.save()
        attachment = Attachment.objects.create(file=_fake_receipt_png(), uploaded_by=self.employee)
        expense = Expense.objects.create(
            employee=self.employee,
            attachment=attachment,
            category=self.category,
            description="Parkering",
            expense_date=date(2026, 1, 5),
            amount="50.00",
        )
        response = self.client.post(reverse("core:approve_item", args=["utlagg", expense.pk]))
        self.assertEqual(response.status_code, 302)
        expense.refresh_from_db()
        self.assertEqual(expense.status, "approved")
        self.assertEqual(expense.decided_by, self.employee)


class RejectedExpenseResubmitTests(TestCase):
    """Regressionstest: resubmit() sparade tidigare bara statusfälten
    (update_fields), så ägarens rättelser gick tyst förlorade."""

    def setUp(self):
        self.employee = CustomUser.objects.create_user(
            email="anna@example.com", password="pw12345678", employment_number="1"
        )
        self.employee.must_change_password = False
        self.employee.save()
        self.approver = CustomUser.objects.create_user(
            email="attestant@example.com", password="pw12345678", employment_number="2", is_approver=True
        )
        self.category = Category.objects.create(name="Resor", code="RES")
        attachment = Attachment.objects.create(file=_fake_receipt_png(), uploaded_by=self.employee)
        self.expense = Expense.objects.create(
            employee=self.employee,
            attachment=attachment,
            category=self.category,
            description="Lunch",
            expense_date=date(2026, 1, 5),
            amount="200.00",
        )
        self.expense.reject(self.approver, "Fel belopp")

    def test_edited_fields_persist_on_resubmit(self):
        client = Client()
        client.login(username="anna@example.com", password="pw12345678")
        response = client.post(
            reverse("expenses:expense_edit", args=[self.expense.pk]),
            {
                "category": self.category.pk,
                "description": "Lunch rättad",
                "expense_date": "2026-01-05",
                "amount": "250.00",
                "vat_amount": "",
                "currency": "SEK",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, "submitted")
        self.assertEqual(self.expense.description, "Lunch rättad")
        self.assertEqual(str(self.expense.amount), "250.00")


class InactiveCategoryEditTests(TestCase):
    """Regressionstest: ett utlägg vars kategori inaktiverats måste ändå
    kunna sparas i redigeringsformuläret med sin befintliga kategori."""

    def test_form_accepts_instances_own_inactive_category(self):
        from expenses.forms import ExpenseForm

        employee = CustomUser.objects.create_user(
            email="anna@example.com", password="pw12345678", employment_number="1"
        )
        category = Category.objects.create(name="Gammal", code="GML", is_active=False)
        attachment = Attachment.objects.create(file=_fake_receipt_png(), uploaded_by=employee)
        expense = Expense.objects.create(
            employee=employee,
            attachment=attachment,
            category=category,
            description="Taxi",
            expense_date=date(2026, 1, 5),
            amount="99.00",
        )
        form = ExpenseForm(
            {
                "category": category.pk,
                "description": "Taxi till möte",
                "expense_date": "2026-01-05",
                "amount": "99.00",
                "vat_amount": "",
                "currency": "SEK",
            },
            instance=expense,
        )
        self.assertTrue(form.is_valid(), form.errors)
