"""Unit tests: money, dates, header mapping, magic bytes, indicators, SSRF guard."""
import pytest

from app.connectors.base import assert_safe_url, is_blocked_ip
from app.parsers import common, indicators


@pytest.mark.parametrize("raw,minor,direction", [
    ("1,234.50", 123450, None), ("Rs 99", 9900, None), ("(500.00)", -50000, None), ("1500 Dr", 150000, "debit"), ("250.5 CR", 25050, "credit"),
    ("-12.34", -1234, None), ("", None, None), (None, None, None),
])
def test_parse_money(raw, minor, direction):
    r = common.parse_money(raw)
    assert r.minor == minor
    assert r.hint_direction == direction
    assert r.raw == ("" if raw is None else str(raw).strip())


def test_money_never_float_and_truncation_flag():
    r = common.parse_money("10.999")
    assert r.minor == 1099 and "amount_truncated_to_2dp" in r.warnings
    assert isinstance(r.minor, int)


def test_ambiguous_date_is_flagged_not_resolved():
    r = common.parse_datetime("03/04/26")
    assert r.precision == "ambiguous"
    assert "ambiguous_date_dd_mm_vs_mm_dd" in r.warnings
    assert r.raw == "03/04/26"


def test_unambiguous_dates():
    assert common.parse_datetime("2026-03-04 10:15:00").precision == "second"
    assert common.parse_datetime("15/03/2026").precision == "day"
    assert common.parse_datetime("not a date").dt is None


def test_header_mapping_variants():
    m, un = common.guess_column_mapping(["Txn Date", "Narration", "Ref No", "Debit", "Credit", "Balance"])
    assert m["datetime"] == "Txn Date" and m["debit"] == "Debit" and m["credit"] == "Credit" and m["reference"] == "Ref No"
    m, un = common.guess_column_mapping(["Date", "Description", "UTR", "Withdrawal Amt", "Deposit Amt", "Closing Balance", "Mystery"])
    assert m["debit"] == "Withdrawal Amt" and m["credit"] == "Deposit Amt" and un == ["Mystery"]


def test_magic_bytes_detect_and_mismatch():
    kind, w = common.detect_kind(b"%PDF-1.4 ...", "statement.csv")
    assert kind == "pdf" and any(x.startswith("extension_mismatch") for x in w)
    assert common.detect_kind(b"\x00\x01\x02binary", "x.csv")[0] == "unknown"
    assert common.detect_kind(b"a,b,c\n1,2,3\n", "x.csv")[0] == "csv"
    assert common.detect_kind(b'{"observations": []}', "x.json")[0] == "json"


def test_indicator_extraction():
    text = "Paid to rohan12@fictbank via https://kyc-update77.test/login ref UTR SYN1234567890AB from A/C XXXX1234, IP 203.0.113.9 call 9876543210"
    kinds = {i.kind: i.value for i in indicators.extract_indicators(text)}
    assert kinds["url"].startswith("https://kyc-update77.test/login")
    assert kinds["domain"] == "kyc-update77.test"
    assert kinds["vpa"] == "rohan12@fictbank"
    assert kinds["utr"] == "SYN1234567890AB"
    assert kinds["ip"] == "203.0.113.9"
    assert kinds["phone"] == "9876543210"
    assert indicators.ip_classification("203.0.113.9") == "documentation"
    assert indicators.ip_classification("10.0.0.1") == "private"


def test_ssrf_guard():
    for ip in ("127.0.0.1", "10.1.2.3", "169.254.169.254", "192.168.1.1", "::1", "203.0.113.5"):
        assert is_blocked_ip(ip)
    assert not is_blocked_ip("8.8.8.8")
    with pytest.raises(ValueError):
        assert_safe_url("http://rdap.org/domain/x", {"rdap.org"})  # not https
    with pytest.raises(ValueError):
        assert_safe_url("https://evil.example/domain/x", {"rdap.org"})  # not allowlisted
    with pytest.raises(ValueError):
        assert_safe_url("https://localhost/", {"localhost"})  # resolves to loopback
