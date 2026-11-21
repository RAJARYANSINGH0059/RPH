"""PDF, DOCX, TXT and image text extraction with page/paragraph locators.

PDF: PyMuPDF text layer first. If a page has no text layer, OCR fallback is attempted only
when an OCR engine is importable; otherwise an explicit `ocr_unavailable` warning is recorded.
Uploaded content is never executed or rendered in a browser.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

PARSER_NAME_PDF = "pdf_text"
PARSER_NAME_DOCX = "docx_text"
PARSER_NAME_TXT = "plain_text"
PARSER_NAME_IMAGE = "image_ocr"


@dataclass
class TextBlock:
    locator: dict  # {"page": n} or {"paragraph": n} or {"line": n}
    text: str
    method: str  # text_layer|ocr|docx_paragraph|docx_table|plain
    confidence: float | None = None


@dataclass
class DocumentResult:
    blocks: list[TextBlock]
    warnings: list[str] = field(default_factory=list)
    page_count: int = 0

    @property
    def full_text(self) -> str:
        return "\n".join(b.text for b in self.blocks)


def _ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401
        import shutil
        return shutil.which("tesseract") is not None
    except Exception:
        return False


def _ocr_image_bytes(png: bytes) -> tuple[str, float | None]:
    import pytesseract
    from PIL import Image
    img = Image.open(io.BytesIO(png))
    text = pytesseract.image_to_string(img)
    return text, None


def parse_pdf_bytes(data: bytes, max_pages: int = 200) -> DocumentResult:
    import fitz  # PyMuPDF

    warnings: list[str] = []
    blocks: list[TextBlock] = []
    doc = fitz.open(stream=data, filetype="pdf")
    if doc.is_encrypted:
        warnings.append("pdf_encrypted")
        return DocumentResult([], warnings, doc.page_count)
    if doc.page_count > max_pages:
        warnings.append(f"page_limit_{max_pages}_applied")
    ocr_ok = None
    for pno in range(min(doc.page_count, max_pages)):
        page = doc[pno]
        text = page.get_text("text") or ""
        if text.strip():
            blocks.append(TextBlock({"page": pno + 1}, text, "text_layer"))
            continue
        # no text layer -> OCR fallback
        if ocr_ok is None:
            ocr_ok = _ocr_available()
        if ocr_ok:
            try:
                pix = page.get_pixmap(dpi=200)
                t, conf = _ocr_image_bytes(pix.tobytes("png"))
                blocks.append(TextBlock({"page": pno + 1}, t, "ocr", conf))
                warnings.append(f"page_{pno + 1}_ocr_used_low_confidence_review_required")
            except Exception as exc:  # pragma: no cover
                warnings.append(f"page_{pno + 1}_ocr_failed:{type(exc).__name__}")
        else:
            warnings.append(f"page_{pno + 1}_no_text_layer_ocr_unavailable")
    return DocumentResult(blocks, warnings, doc.page_count)


def parse_docx_bytes(data: bytes) -> DocumentResult:
    import docx

    d = docx.Document(io.BytesIO(data))
    blocks: list[TextBlock] = []
    for i, p in enumerate(d.paragraphs, start=1):
        if p.text.strip():
            blocks.append(TextBlock({"paragraph": i}, p.text, "docx_paragraph"))
    for ti, table in enumerate(d.tables, start=1):
        for ri, row in enumerate(table.rows, start=1):
            cells = [c.text for c in row.cells]
            blocks.append(TextBlock({"table": ti, "row": ri}, " | ".join(cells), "docx_table"))
    return DocumentResult(blocks, [], 1)


def parse_txt_bytes(data: bytes) -> DocumentResult:
    warnings: list[str] = []
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
        warnings.append("decoded_as_latin1")
    blocks = [TextBlock({"line": i}, line, "plain") for i, line in enumerate(text.splitlines(), start=1) if line.strip()]
    return DocumentResult(blocks, warnings, 1)


def parse_image_bytes(data: bytes) -> DocumentResult:
    warnings: list[str] = []
    if not _ocr_available():
        return DocumentResult([], ["ocr_unavailable_image_stored_for_manual_review"], 1)
    try:
        text, conf = _ocr_image_bytes(data)
        warnings.append("ocr_used_low_confidence_review_required")
        return DocumentResult([TextBlock({"page": 1}, text, "ocr", conf)], warnings, 1)
    except Exception as exc:  # pragma: no cover
        return DocumentResult([], [f"ocr_failed:{type(exc).__name__}"], 1)
