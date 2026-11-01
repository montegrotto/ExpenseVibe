"""Klient mot ReInvGrabber, ett separat internt program som läser
bokförings-/betalningsfält (belopp, moms, leverantör, OCR-referens, ...) ur
en uppladdad bilaga med lokal OCR. Körs som en egen, alltid igång tjänst -
INTE i samma process som ExpenseVibe, dels för att slippa Tesseract-
verktygskedjan i ExpenseVibes egen körmiljö, dels för att undvika en
Python-versionskrock.

Anropet är avsiktligt "best effort": en extraherad summa är bara ett
förslag som användaren ändå kan ändra i formuläret, så ett trasigt/nere
ReInvGrabber-anrop ska ALDRIG stoppa själva bilageuppladdningen - varje fel
fångas och loggas här, aldrig kastas vidare till anroparen.
"""

import json
import logging
import mimetypes
import uuid
from urllib import error as urllib_error
from urllib import request as urllib_request

from django.conf import settings

logger = logging.getLogger(__name__)


def _build_multipart_body(file_name, file_bytes, fields):
    boundary = uuid.uuid4().hex
    content_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    parts = []
    for key, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode("utf-8"))
    parts.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n".encode("utf-8")
        + file_bytes
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def extract_fields(file_bytes, file_name):
    """Anropar ReInvGrabbers /process-one med EN bilaga och returnerar dess
    extraherade fält som dict, eller None om tjänsten inte är konfigurerad,
    inte svarar, eller svarar med ett fel - aldrig en exception (se
    modulens docstring för varför)."""
    base_url = (getattr(settings, "REINVGRABBER_URL", "") or "").strip().rstrip("/")
    if not base_url:
        return None

    try:
        timeout = int(getattr(settings, "REINVGRABBER_TIMEOUT", 15) or 15)
        body, content_type = _build_multipart_body(file_name, file_bytes, {})

        request = urllib_request.Request(
            f"{base_url}/process-one",
            data=body,
            headers={"Content-Type": content_type, "Accept": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib_error.HTTPError, urllib_error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.warning("ReInvGrabber-anrop misslyckades för %s: %s", file_name, exc)
        return None
    except Exception:
        # Sista skyddsnätet - se modulens docstring: EN oväntad bugg här
        # (eller ett oväntat svarsformat) får ALDRIG stoppa uppladdningen,
        # bara innebära att inget föreslås.
        logger.exception("Oväntat fel vid ReInvGrabber-anrop för %s", file_name)
        return None

    if not isinstance(payload, dict) or "error" in payload:
        logger.warning("ReInvGrabber gav ett oanvändbart svar för %s: %r", file_name, payload)
        return None
    return payload
