import logging

from attachments.extraction_client import extract_fields

logger = logging.getLogger(__name__)


def _fetch_extracted_data(attachment):
    """Best-effort: returnerar None (kastar aldrig) om integrationen är
    avstängd, nere, timeoutar, eller filen inte går att läsa tillbaka - se
    extraction_client-modulens docstring. Uppladdningen ska ALDRIG stoppas
    av det här steget - i värsta fall uteblir bara förslaget."""
    if not attachment.file:
        return None
    try:
        attachment.file.open("rb")
        try:
            file_bytes = attachment.file.read()
        finally:
            if not attachment.file.closed:
                attachment.file.close()
        return extract_fields(file_bytes, attachment.file_name)
    except Exception:
        logger.exception("Kunde inte läsa bilagan för ReInvGrabber-anrop: %s", attachment.file_name)
        return None


def save_attachment_with_thumbnail(attachment):
    attachment.save()
    update_fields = []
    if attachment.generate_thumbnail():
        update_fields += ["thumbnail", "thumbnail_generated_at"]

    extracted = _fetch_extracted_data(attachment)
    if extracted is not None:
        attachment.extracted_data = extracted
        update_fields.append("extracted_data")

    if update_fields:
        attachment.save(update_fields=update_fields)
