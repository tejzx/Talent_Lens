"""OCR helpers. Degrade gracefully when tesseract/poppler are unavailable."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def ocr_pdf_bytes(data: bytes, dpi: int = 200, max_pages: int = 10) -> str:
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
    except Exception as exc:  # pragma: no cover - optional dependency
        log.warning("OCR unavailable: %s", exc)
        return ""

    try:
        images = convert_from_bytes(data, dpi=dpi, first_page=1, last_page=max_pages)
    except Exception as exc:  # pragma: no cover - poppler missing
        log.warning("pdf2image failed: %s", exc)
        return ""

    out: list[str] = []
    for image in images:
        try:
            out.append(pytesseract.image_to_string(image))
        except Exception as exc:  # pragma: no cover
            log.warning("tesseract failed: %s", exc)
            break
    return "\n".join(out).strip()
