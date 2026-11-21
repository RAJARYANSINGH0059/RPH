"""OCR engine abstraction.

Engine order: Tesseract (pytesseract + binary; English + Hindi when trained data present) -> RapidOCR (ONNX, pure
Python, English/Latin) -> none. Controlled by OCR_ENGINE=auto|tesseract|rapidocr|off. Every result carries the engine
name/version, a mean confidence (0-1) where the engine provides it, and a quality flag. Low-confidence text is
`review_required`; the caller must not promote it to a high-confidence edge without corroboration.
"""
from __future__ import annotations

import io
import os
import shutil
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass
class OcrResult:
    text: str
    engine: str
    engine_version: str
    confidence: float | None  # 0..1 mean word/line confidence
    quality: str  # ok|low|unknown
    boxes: list[dict] = field(default_factory=list)  # {text, conf, bbox:[x0,y0,x1,y1]}
    warnings: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)

    @property
    def review_required(self) -> bool:
        return self.quality != "ok"


LOW_CONF = 0.75


def _mode() -> str:
    return os.environ.get("OCR_ENGINE", "auto").lower()


@lru_cache
def tesseract_info() -> dict:
    try:
        import pytesseract
    except Exception:
        return {"available": False, "reason": "pytesseract not installed"}
    binary = shutil.which("tesseract") or os.environ.get("TESSERACT_CMD")
    if not binary:
        return {"available": False, "reason": "tesseract binary not found"}
    pytesseract.pytesseract.tesseract_cmd = binary
    try:
        ver = str(pytesseract.get_tesseract_version())
        langs = pytesseract.get_languages(config="")
    except Exception as exc:
        return {"available": False, "reason": f"tesseract error: {type(exc).__name__}"}
    return {"available": True, "version": ver, "languages": langs}


@lru_cache
def rapidocr_info() -> dict:
    try:
        import importlib.metadata as md
        import rapidocr_onnxruntime  # noqa: F401
        return {"available": True, "version": md.version("rapidocr-onnxruntime"), "languages": ["en"]}
    except Exception as exc:
        return {"available": False, "reason": f"rapidocr not installed ({type(exc).__name__})"}


def status() -> dict:
    mode = _mode()
    t, r = tesseract_info(), rapidocr_info()
    active = None
    if mode in {"auto", "tesseract"} and t["available"]:
        active = "tesseract"
    elif mode in {"auto", "rapidocr"} and r["available"]:
        active = "rapidocr"
    if mode == "off":
        active = None
    return {"mode": mode, "active_engine": active, "tesseract": t, "rapidocr": r}


@lru_cache
def _rapid():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()


def ocr_image(data: bytes) -> OcrResult | None:
    """Return None when no engine is available (caller records an explicit warning)."""
    st = status()
    eng = st["active_engine"]
    if eng is None:
        return None
    from PIL import Image
    img = Image.open(io.BytesIO(data)).convert("RGB")
    if eng == "tesseract":
        import pytesseract
        langs = [l for l in ("eng", "hin") if l in tesseract_info().get("languages", [])] or ["eng"]
        d = pytesseract.image_to_data(img, lang="+".join(langs), output_type=pytesseract.Output.DICT)
        boxes, confs, words = [], [], []
        for i, w in enumerate(d["text"]):
            if not w.strip():
                continue
            c = float(d["conf"][i])
            if c < 0:
                continue
            confs.append(c / 100)
            words.append(w)
            boxes.append({"text": w, "conf": round(c / 100, 3), "bbox": [d["left"][i], d["top"][i], d["left"][i] + d["width"][i], d["top"][i] + d["height"][i]]})
        text = pytesseract.image_to_string(img, lang="+".join(langs))
        conf = sum(confs) / len(confs) if confs else None
        return OcrResult(text, "tesseract", tesseract_info()["version"], conf, "ok" if conf is not None and conf >= LOW_CONF else ("low" if conf is not None else "unknown"),
                         boxes, [] if words else ["ocr_no_text_detected"], langs)
    # rapidocr
    import numpy as np
    arr = np.array(img)
    result, _ = _rapid()(arr)
    boxes, lines, confs = [], [], []
    for item in result or []:
        pts, txt, c = item
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        boxes.append({"text": txt, "conf": round(float(c), 3), "bbox": [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]})
        lines.append(txt)
        confs.append(float(c))
    conf = sum(confs) / len(confs) if confs else None
    return OcrResult("\n".join(lines), "rapidocr", rapidocr_info()["version"], conf, "ok" if conf is not None and conf >= LOW_CONF else ("low" if conf is not None else "unknown"),
                     boxes, [] if lines else ["ocr_no_text_detected"], ["en"])
