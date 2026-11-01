import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase


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
