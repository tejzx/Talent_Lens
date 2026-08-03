"""PDF text extraction with automatic OCR fallback."""
from __future__ import annotations

from .ocr import ocr_pdf_bytes

MIN_CHARS_PER_PAGE = 80


def extract_pdf_text(data: bytes) -> str:
    """Extract text from a PDF. Falls back to OCR for scanned documents."""
    import fitz  # PyMuPDF, imported lazily

    text_parts: list[str] = []
    page_count = 0
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            page_count = doc.page_count
            for page in doc:
                text_parts.append(page.get_text("text"))
    except Exception:
        return ocr_pdf_bytes(data)

    text = "\n".join(text_parts).strip()
    if page_count and len(text) < MIN_CHARS_PER_PAGE * page_count:
        ocr_text = ocr_pdf_bytes(data)
        if len(ocr_text) > len(text):
            return ocr_text
    return text
