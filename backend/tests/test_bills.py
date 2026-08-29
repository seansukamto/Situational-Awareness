import json

import pytest

from app.projects.bills import parse_bill_bytes


def test_parse_json_bill():
    payload = {
        "period_start": "2026-07-01",
        "period_end": "2026-07-31",
        "total_kwh": 4860,
        "total_cost_sgd": 1550.83,
    }
    bill = parse_bill_bytes("bill.json", json.dumps(payload).encode())
    assert bill.total_kwh == 4860
    assert bill.total_cost_sgd == 1550.83
    assert bill.evidence[0].source == "bill.json"


def test_parse_text_bill():
    text = b"""
    Billing period 2026-07-01 to 2026-07-31
    Total electricity consumption 4,860 kWh
    Total amount SGD 1,550.83
    """
    bill = parse_bill_bytes("bill.txt", text)
    assert bill.period_start == "2026-07-01"
    assert bill.total_kwh == 4860


def test_reject_incomplete_bill():
    with pytest.raises(ValueError, match="Could not find"):
        parse_bill_bytes("bill.txt", b"amount only")
