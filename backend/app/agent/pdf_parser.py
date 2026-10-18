from __future__ import annotations

from io import BytesIO


class PdfExtractionError(ValueError):
    """Indicates that a PDF could not be read as text."""


def extract_text(content: bytes) -> str:
    """Extract text from all pages of a PDF without persisting the upload."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - exercised in deployment misconfiguration
        raise PdfExtractionError("PDF support is not installed") from exc

    try:
        reader = PdfReader(BytesIO(content), strict=False)
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # pypdf exposes several parser-specific exceptions
        raise PdfExtractionError("The PDF could not be read") from exc

    text = "\n".join(pages).strip()
    if not text:
        raise PdfExtractionError("The PDF contains no extractable text")
    return text
