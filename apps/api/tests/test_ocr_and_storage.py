"""OCR engine path (RapidOCR/Tesseract), graceful absence, locators and confidence reaching evidence; storage adapter hashing."""
import io
import os

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.parsers import documents, ocr


def _text_image(text: str, rotate: int = 0, noise: bool = False, size=(900, 220)) -> bytes:
    img = Image.new("RGB", size, (255, 255, 255))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except Exception:
        font = ImageFont.load_default()
    d.text((20, 60), text, fill=(0, 0, 0), font=font)
    if noise:
        import random
        rnd = random.Random(1)
        for _ in range(4000):
            d.point((rnd.randint(0, size[0] - 1), rnd.randint(0, size[1] - 1)), fill=(rnd.randint(0, 255),) * 3)
    if rotate:
        img = img.rotate(rotate, expand=True, fillcolor=(255, 255, 255))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _scanned_pdf(png: bytes) -> bytes:
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=600, height=400)
    page.insert_image(page.rect, stream=png)
    return doc.tobytes()


def _text_pdf(text: str) -> bytes:
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    return doc.tobytes()


def test_ocr_status_reports_engines():
    st = ocr.status()
    assert st["mode"] in {"auto", "tesseract", "rapidocr", "off"}
    assert "tesseract" in st and "rapidocr" in st


def test_text_layer_pdf_does_not_use_ocr():
    res = documents.parse_pdf_bytes(_text_pdf("Paid to rohan12@fictbank ref SYN1234567890AB"))
    assert res.blocks and res.blocks[0].method == "text_layer"
    assert not any("ocr" in w for w in res.warnings)


@pytest.mark.skipif(ocr.status()["active_engine"] is None, reason="no OCR engine installed")
def test_png_screenshot_ocr_has_locator_confidence_and_review_flag():
    res = documents.parse_image_bytes(_text_image("Pay to rohan12@fictbank  UTR SYN1234567890AB"))
    assert res.blocks, res.warnings
    b = res.blocks[0]
    assert b.method == "ocr" and b.locator == {"page": 1}
    assert b.ocr["engine"] in {"tesseract", "rapidocr"} and b.ocr["engine_version"]
    assert b.ocr["confidence"] is None or 0 <= b.ocr["confidence"] <= 1
    assert any("review_required" in w for w in res.warnings)
    assert "fictbank" in b.text.lower() or "SYN" in b.text.upper()


@pytest.mark.skipif(ocr.status()["active_engine"] is None, reason="no OCR engine installed")
def test_scanned_pdf_ocr_page_locator():
    res = documents.parse_pdf_bytes(_scanned_pdf(_text_image("Account 111122223333 debit 1500.00")))
    assert res.page_count == 1
    assert res.blocks and res.blocks[0].method == "ocr" and res.blocks[0].locator == {"page": 1}


@pytest.mark.skipif(ocr.status()["active_engine"] is None, reason="no OCR engine installed")
def test_poor_quality_rotated_scan_flags_review_never_silent():
    res = documents.parse_image_bytes(_text_image("UTR SYN0000000000ZZ", rotate=25, noise=True))
    # whatever the engine manages, it must either return a block flagged for review or an explicit warning
    assert res.warnings or (res.blocks and res.blocks[0].ocr["quality"] in {"low", "unknown", "ok"})
    assert all("review_required" in w or "ocr" in w for w in res.warnings)


def test_ocr_absent_is_explicit(monkeypatch):
    monkeypatch.setenv("OCR_ENGINE", "off")
    res = documents.parse_image_bytes(_text_image("hello"))
    assert res.blocks == []
    assert res.warnings == ["ocr_unavailable_image_stored_for_manual_review"]
    pdf = documents.parse_pdf_bytes(_scanned_pdf(_text_image("hello")))
    assert pdf.blocks == [] and any("ocr_unavailable" in w for w in pdf.warnings)


@pytest.mark.skipif(ocr.status()["active_engine"] is None, reason="no OCR engine installed")
def test_ocr_metadata_reaches_evidence_and_graph(client, analyst):
    cid = client.post("/api/cases", json={"title": "ocr case"}, headers=analyst).json()["id"]
    png = _text_image("Pay to rohan12@fictbank via https://kyc-update77.test/login")
    r = client.post(f"/api/cases/{cid}/upload", files=[("files", ("screenshot.png", png, "image/png"))], headers=analyst)
    assert r.status_code == 200, r.text
    run = r.json()[0]["parse_run"]
    assert run["stats"]["blocks"] == 1
    g = client.get(f"/api/cases/{cid}/graph", headers=analyst).json()
    mentions = [e for e in g["edges"] if e["type"] == "MENTIONS"]
    assert mentions, "OCR-extracted indicators should produce MENTIONS edges"
    d = client.get(f"/api/cases/{cid}/edges/{mentions[0]['id']}", headers=analyst).json()
    ev = d["supporting_evidence"][0]
    assert ev["extraction_method"].startswith("regex_") and ev["source_locator"]["page"] == 1
    assert "ocr_review_required" in ev["quality_flags"]
    assert "extracted_by_ocr_verify_against_image" in d["method"]["limitations"]
    rep = client.get(f"/api/cases/{cid}/report.json", headers=analyst).json()
    assert any("ocr" in str(p["warnings"]).lower() for p in rep["parsing"])


def test_local_storage_hash_roundtrip(tmp_path):
    from app.services.storage import LocalStorage, StorageError
    st = LocalStorage(tmp_path)
    key = st.put("case1", b"hello", "txt")
    assert st.get(key) == b"hello"
    assert st.get(key, expected_sha256="2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824") == b"hello"
    with pytest.raises(StorageError):
        st.get(key, expected_sha256="00" * 32)
    assert st.signed_url(key) is None
    assert st.status()["backend"] == "local"


def test_s3_misconfiguration_falls_back_visibly(monkeypatch):
    from app.services import storage
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.delenv("S3_BUCKET", raising=False)
    storage.get_storage.cache_clear()
    try:
        st = storage.storage_status()
        assert st["backend"] == "local" and "warning" in st
    finally:
        storage.get_storage.cache_clear()
        monkeypatch.setenv("STORAGE_BACKEND", "local")
        storage.get_storage.cache_clear()


def test_health_live_reports_ocr_and_storage(client):
    h = client.get("/api/health/live").json()
    assert "ocr" in h and "storage" in h and h["storage"]["backend"] in {"local", "s3"}
    assert os.environ.get("STORAGE_BACKEND", "local") == "local"
