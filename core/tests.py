import io
import os
import runpy
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from absence.models import Period, TimeReport
from attachments.models import Attachment
from expenses.models import Expense
from export.models import ExportBatch
from mileage.models import MileageReport


class SecretKeySettingsTests(SimpleTestCase):
    def _import_settings(self, **env):
        return subprocess.run(
            [sys.executable, "-c", "import expensevibe.settings"],
            cwd=settings.BASE_DIR,
            env={**os.environ, **env},
            capture_output=True,
            text=True,
        )

    def test_missing_key_without_debug_refuses_to_start(self):
        result = self._import_settings(DJANGO_DEBUG="0", DJANGO_SECRET_KEY="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", result.stderr)

    def test_missing_key_with_debug_uses_dev_fallback(self):
        result = self._import_settings(DJANGO_DEBUG="1", DJANGO_SECRET_KEY="")
        self.assertEqual(result.returncode, 0, result.stderr)


class SeedDemoTests(TestCase):
    def test_seed_demo_fills_database_and_refuses_to_run_twice(self):
        script = Path(settings.BASE_DIR) / "scripts" / "seed_demo.py"
        with (
            patch.dict(os.environ, {"DEMO_PASSWORD": "demo"}),
            override_settings(MEDIA_ROOT=tempfile.mkdtemp()),
            redirect_stdout(io.StringIO()),
        ):
            runpy.run_path(script)
            with self.assertRaises(SystemExit):
                runpy.run_path(script)

        user = get_user_model().objects.get(email="erik@demo.expensevibe.se")
        self.assertTrue(user.check_password("demo"))
        self.assertFalse(user.must_change_password)
        self.assertTrue(get_user_model().objects.get(email="attestant@demo.expensevibe.se").is_approver)
        self.assertEqual(Expense.objects.filter(status="exported").count(), 3)
        self.assertEqual(Expense.objects.filter(status="rejected", employee=user).count(), 1)
        self.assertEqual(MileageReport.objects.filter(status="submitted").count(), 2)
        self.assertEqual(TimeReport.objects.filter(status="exported").count(), 2)
        self.assertEqual(Period.objects.filter(status="reported").count(), 1)
        self.assertEqual(Attachment.objects.filter(expense__isnull=True).count(), 3)
        batch = ExportBatch.objects.get()
        self.assertEqual(batch.row_count, 7)
        self.assertIn(b"SalaryData", batch.file.read())
