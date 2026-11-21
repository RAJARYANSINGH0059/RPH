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
    ocr: dict | None = None  # engine, version, confidence, quality, boxes


@dataclass
class DocumentResult:
    blocks: list[TextBlock]
    warnings: list[str] = field(default_factory=list)
    page_count: int = 0

    @property
    def full_text(self) -> str:
        return "\n".join(b.text for b in self.blocks)


def _ocr_block(png: bytes, locator: dict) -> tuple["TextBlock | None", list[str]]:
    """Run the configured OCR engine; return (block, warnings). Block is None when no engine is available."""
    from app.parsers import ocr as ocr_mod
    res = ocr_mod.ocr_image(png)
    loc_s = ",".join(f"{k} {v}" for k, v in locator.items())
    if res is None:
        return None, [f"{loc_s}: no_text_layer_ocr_unavailable_manual_review_required"]
    state = "low_confidence" if res.quality != "ok" else "used"
    warnings = [f"{loc_s}: ocr_{res.engine}_{state}_review_required"] + [f"{loc_s}: {w}" for w in res.warnings]
    block = TextBlock(locator, res.text, "ocr", res.confidence)
    block.ocr = {"engine": res.engine, "engine_version": res.engine_version, "confidence": res.confidence, "quality": res.quality,
                 "languages": res.languages, "boxes": res.boxes[:200]}
    return block, warnings


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
    for pno in range(min(doc.page_count, max_pages)):
        page = doc[pno]
        text = page.get_text("text") or ""
        if text.strip():
            blocks.append(TextBlock({"page": pno + 1}, text, "text_layer"))
            continue
        # no text layer -> OCR fallback through the configured engine
        try:
            pix = page.get_pixmap(dpi=200)
            block, w = _ocr_block(pix.tobytes("png"), {"page": pno + 1})
            warnings += w
            if block is not None:
                blocks.append(block)
        except Exception as exc:  # pragma: no cover
            warnings.append(f"page_{pno + 1}_ocr_failed:{type(exc).__name__}")
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
    try:
        block, warnings = _ocr_block(data, {"page": 1})
    except Exception as exc:  # pragma: no cover
        return DocumentResult([], [f"ocr_failed:{type(exc).__name__}"], 1)
    if block is None:
        return DocumentResult([], ["ocr_unavailable_image_stored_for_manual_review"], 1)
    return DocumentResult([block], warnings, 1)
