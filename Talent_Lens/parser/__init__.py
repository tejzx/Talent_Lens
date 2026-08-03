"""Document parsing layer: PDF, DOCX, TXT with OCR fallback."""
from __future__ import annotations

from .docx_parser import extract_docx_text
from .pdf_parser import extract_pdf_text

__all__ = ["extract_docx_text", "extract_pdf_text", "extract_text"]


def extract_text(filename: str, data: bytes) -> str:
    """Route a file to the right parser based on its extension."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return extract_pdf_text(data)
    if name.endswith(".docx"):
        return extract_docx_text(data)
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="ignore").strip()
    # Unknown extension: best-effort PDF, then plain text.
    try:
        return extract_pdf_text(data)
    except Exception:
        return data.decode("utf-8", errors="ignore").strip()
