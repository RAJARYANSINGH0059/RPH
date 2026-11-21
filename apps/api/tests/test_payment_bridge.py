"""QR / UPI payload parsing and payment-instruction-to-transaction matching."""
import io

import pytest

from app.parsers import qr
from app.synthetic.mirage import qr_png


def test_upi_payload_parsing_preserves_raw_and_unknown_params():
    p = qr.parse_payment_payload("upi://pay?pa=Collect-Example@bank&pn=Example%20Merchant&am=45000.00&cu=INR&tn=Application%20Fee&tr=REF-ABC-123&mystery=1")
    assert p.payload_type == "upi" and p.payee_vpa == "collect-example@bank" and p.payee_vpa_raw == "Collect-Example@bank"
    assert p.amount_minor == 4500000 and p.currency == "INR" and p.reference == "REF-ABC-123" and p.payee_name_raw == "Example Merchant" and p.note_raw == "Application Fee"
    assert p.fields["mystery"] == "1" and any(w.startswith("unknown_parameter_preserved:mystery") for w in p.warnings)


@pytest.mark.parametrize("payload,ptype,warn", [
    ("", "invalid", "empty_payload"),
    ("hello world", "unsupported", "payload_format_not_recognised_as_payment_instruction"),
    ("upi://pay?pa=x@bank&am=abc&cu=INR", "upi", "amount_not_numeric"),
    ("upi://pay?pa=x@bank&am=10.00&cu=USD", "upi", "unsupported_currency:USD"),
    ("upi://pay?pa=x@bank&am=10.00", "upi", "currency_missing_not_assumed"),
    ("upi://pay?am=10.00&cu=INR", "upi", "payee_missing"),
    ("someone@bank", "text", "bare_vpa_without_parameters"),
    ("https://pay.example.test/checkout?id=9", "url", "url_payload_without_upi_parameters_stored_as_evidence_string_not_opened"),
])
def test_payload_classification_and_warnings(payload, ptype, warn):
    p = qr.parse_payment_payload(payload)
    assert p.payload_type == ptype and warn in p.warnings


def test_qr_decode_clean_multi_rotated_and_damaged():
    from PIL import Image
    png = qr_png("upi://pay?pa=a@bank&am=10.00&cu=INR&tr=R1")
    out, w = qr.decode_qr(png)
    assert len(out) == 1 and out[0].payload.startswith("upi://pay?pa=a@bank")
    # two codes on one page
    a, b = Image.open(io.BytesIO(qr_png("upi://pay?pa=a@bank&am=1.00&cu=INR"))), Image.open(io.BytesIO(qr_png("upi://pay?pa=b@bank&am=2.00&cu=INR")))
    page = Image.new("RGB", (a.width + b.width + 60, max(a.height, b.height) + 40), "white")
    page.paste(a, (20, 20))
    page.paste(b, (a.width + 40, 20))
    buf = io.BytesIO()
    page.save(buf, format="PNG")
    out, w = qr.decode_qr(buf.getvalue())
    assert {o.payload.split("pa=")[1][:6] for o in out} == {"a@bank", "b@bank"}
    # rotated photograph
    rot = Image.open(io.BytesIO(png)).rotate(90, expand=True)
    buf = io.BytesIO()
    rot.save(buf, format="PNG")
    out, w = qr.decode_qr(buf.getvalue())
    assert len(out) == 1
    # heavily damaged: half the image blanked -> no decode, explicit warning, no invented payload
    img = Image.open(io.BytesIO(png)).convert("RGB")
    for x in range(img.width // 2, img.width):
        for y in range(img.height):
            img.putpixel((x, y), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    out, w = qr.decode_qr(buf.getvalue())
    assert out == [] and "no_qr_code_decoded" in w


@pytest.fixture(scope="module")
def mirage(client, analyst):
    r = client.post("/api/synthetic/generate", json={"scenario_type": "desert_mirage", "difficulty": "messy", "size": "small", "seed": 1001}, headers=analyst)
    assert r.status_code == 201, r.text
    return r.json()["case"]["id"]


def test_mirage_qr_and_link_match_exactly(client, analyst, mirage):
    r = client.get(f"/api/cases/{mirage}/payment-instructions", headers=analyst)
    assert r.status_code == 200
    pis = r.json()["instructions"]
    assert {p["extraction_method"] for p in pis} >= {"qr_decoder", "uri_text"}
    for p in pis:
        m = client.post(f"/api/cases/{mirage}/payment-instructions/{p['id']}/match", headers=analyst).json()
        assert m["match_status"] == "EXACT_REFERENCE_AND_IDENTIFIER", m["match_status"]
        best = m["candidates"][0]
        assert "reference" in best["matched_fields"] and not best["conflicting_fields"]
        assert any("does not by itself identify the human" in lim for lim in m["limitations"])
    g = client.get(f"/api/cases/{mirage}/graph", headers=analyst).json()
    assert any(e["type"] == "PAYMENT_INSTRUCTION_MATCHES_TRANSACTION" and e["evidence_level"] == "corroborated" for e in g["edges"])


def test_manual_instruction_levels(client, analyst, mirage):
    txs = client.get(f"/api/cases/{mirage}/transactions", headers=analyst).json()
    t = next(x for x in txs if x["counterparty_ref"] and "@" in x["counterparty_ref"] and x["amount_minor"] and x["external_reference"])
    vpa, amt, ref = t["counterparty_ref"], t["amount_minor"], t["external_reference"]
    post = lambda payload: client.post(f"/api/cases/{mirage}/payment-instructions", json={"raw_payload": payload}, headers=analyst).json()  # noqa: E731
    assert post(f"upi://pay?pa={vpa}&am={amt / 100:.2f}&cu=INR")["match_status"] == "EXACT_IDENTIFIER_AMOUNT"
    assert post(f"upi://pay?pa={vpa}&am={(amt + 100) / 100:.2f}&cu=INR")["match_status"] == "CONFLICTED_MATCH"
    one_char = vpa[:-1] + ("x" if vpa[-1] != "x" else "y")
    assert post(f"upi://pay?pa={one_char}&am={amt / 100:.2f}&cu=INR")["match_status"] == "NO_MATCH"
    r = post(f"upi://pay?pa={vpa}&am={amt / 100:.2f}&cu=USD")
    assert r["match_status"] == "CONFLICTED_MATCH" and "unsupported_currency:USD" in r["warnings"]
    assert post("upi://pay?pn=Only%20Name&am=1.00&cu=INR")["match_status"] == "UNRESOLVED"  # name only can never match
    r = post(f"upi://pay?pa={vpa}&tr={ref}&am={amt / 100:.2f}&cu=INR")
    assert r["match_status"] == "EXACT_REFERENCE_AND_IDENTIFIER"


def test_decode_image_endpoint_and_report(client, analyst, mirage):
    png = qr_png("upi://pay?pa=nobody@fictbank&am=99.00&cu=INR&tr=NOPE1")
    r = client.post(f"/api/cases/{mirage}/payment-instructions/decode-image", files={"file": ("qr.png", png, "image/png")}, headers=analyst)
    assert r.status_code == 201 and r.json()["decoded"] == 1 and r.json()["results"][0]["match_status"] == "NO_MATCH"
    r = client.get(f"/api/cases/{mirage}/payment-instructions/report.pdf", headers=analyst)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"


def test_other_user_cannot_see_instructions(client, other_analyst, mirage):
    assert client.get(f"/api/cases/{mirage}/payment-instructions", headers=other_analyst).status_code == 404
