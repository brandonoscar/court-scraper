"""Tests for the OSCN harvester's parser, run against REAL OSCN HTML.

The two fixtures in oscn_fixtures/ are genuine OSCN GetCaseInformation pages
(decoded from the repo's VCR cassettes), so these tests pin the parser's
behavior on real-world markup, not mocks.
"""
import importlib.util
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_HARVESTER = os.path.join(os.path.dirname(_HERE), "harvest_oscn.py")
_spec = importlib.util.spec_from_file_location("harvest_oscn", _HARVESTER)
harvest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harvest)


def _fixture(name):
    with open(os.path.join(_HERE, "oscn_fixtures", name)) as fh:
        return fh.read()


def test_parses_premises_liability_case():
    rec = harvest.parse_case(_fixture("oscn_CJ-2018-2919.html"), "tulsa", "CJ-2018-2919")
    assert rec["case_number"] == "CJ-2018-2919"
    assert rec["source_place_id"] == "ok_tulsa"
    assert "PREMISES LIABILITY" in rec["case_type"]
    assert rec["file_date"] == "07/12/2018"
    assert rec["plaintiffs"] == ["BROWN, SHELBY"]
    assert "WAL MART SUPERCENTER" in rec["defendants"]
    assert rec["last_activity_date"] == "02/17/2019"
    # No JUDGMENT docket entry on this case -> no judgment captured.
    assert rec["judgment_date"] is None
    assert rec["judgment_amount"] is None


def test_parses_foreclosure_case_parties():
    rec = harvest.parse_case(_fixture("oscn_CJ-2021-2045.html"), "tulsa", "CJ-2021-2045")
    assert "FORECLOSURE" in rec["case_type"]
    assert rec["plaintiffs"] == ["U S BANK NATIONAL ASSOCIATION"]
    assert any("MIZE" in d for d in rec["defendants"])
    assert rec["file_date"] == "07/15/2021"


def test_invalid_page_returns_none():
    assert harvest.parse_case("<html><body>nope</body></html>", "tulsa", "CJ-9999-1") is None


def test_best_amount_picks_largest_in_judgment_rows():
    rows = [
        {"code": "J", "description": "JOURNAL ENTRY OF JUDGMENT $1,200.00 plus costs"},
        {"code": "J", "description": "AMENDED JUDGMENT total $24,500.00"},
    ]
    assert harvest._best_amount(rows) == "$24,500.00"


def test_norm_date():
    assert harvest._norm_date("07-12-2018") == "07/12/2018"
    assert harvest._norm_date("Date") is None
