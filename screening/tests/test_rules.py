"""Unit tests for the hard-coded screening rules.

These pin the verdict of each rule so the audit trail can't silently drift.
Run: python -m pytest screening/tests/ -q
"""
from datetime import date

from screening.models import JudgmentRecord
from screening.rules import (
    rule_amount_floor,
    rule_case_type_exclude,
    rule_dormancy,
    rule_judgment_age,
)

AS_OF = date(2026, 6, 28)


def _rec(**kw):
    base = dict(source_place_id="ga_dekalb", case_number="X")
    base.update(kw)
    return JudgmentRecord(**base)


# ---- case_type_exclude ----------------------------------------------------
def test_eviction_case_type_is_excluded():
    cfg = {"exclude_keywords": ["dispossess", "eviction"]}
    rec = _rec(case_type="Magistrate Dispossessory - Non Payment of Rent")
    assert rule_case_type_exclude(rec, cfg, AS_OF).passed is False


def test_civil_account_case_type_passes():
    cfg = {"exclude_keywords": ["dispossess", "eviction"]}
    rec = _rec(case_type="Civil - Open Account")
    assert rule_case_type_exclude(rec, cfg, AS_OF).passed is True


# ---- judgment_age ---------------------------------------------------------
def test_age_inside_band_passes():
    cfg = {"min_years": 8, "max_years": 15}
    rec = _rec(date_entered=date(2015, 1, 1))  # ~11.5y
    assert rule_judgment_age(rec, cfg, AS_OF).passed is True


def test_age_too_recent_fails():
    cfg = {"min_years": 8, "max_years": 15}
    rec = _rec(date_entered=date(2022, 1, 1))
    assert rule_judgment_age(rec, cfg, AS_OF).passed is False


def test_age_too_old_fails():
    cfg = {"min_years": 8, "max_years": 15}
    rec = _rec(date_entered=date(2008, 1, 1))
    assert rule_judgment_age(rec, cfg, AS_OF).passed is False


def test_age_missing_date_fails_safe():
    cfg = {"min_years": 8, "max_years": 15}
    assert rule_judgment_age(_rec(), cfg, AS_OF).passed is False


# ---- dormancy -------------------------------------------------------------
def test_no_enforcement_ever_is_dormant():
    cfg = {"inactive_years": 5}
    rec = _rec(last_enforcement_date=None)
    assert rule_dormancy(rec, cfg, AS_OF).passed is True


def test_old_enforcement_is_dormant():
    cfg = {"inactive_years": 5}
    rec = _rec(last_enforcement_date=date(2016, 1, 1))
    assert rule_dormancy(rec, cfg, AS_OF).passed is True


def test_recent_enforcement_is_active():
    cfg = {"inactive_years": 5}
    rec = _rec(last_enforcement_date=date(2024, 3, 15))
    assert rule_dormancy(rec, cfg, AS_OF).passed is False


# ---- amount_floor ---------------------------------------------------------
def test_amount_above_floor_passes():
    cfg = {"min_amount": 20000.0}
    assert rule_amount_floor(_rec(judgment_amount=24150.0), cfg, AS_OF).passed is True


def test_amount_below_floor_fails():
    cfg = {"min_amount": 20000.0}
    assert rule_amount_floor(_rec(judgment_amount=18500.0), cfg, AS_OF).passed is False


def test_amount_unknown_fails_safe():
    cfg = {"min_amount": 20000.0}
    assert rule_amount_floor(_rec(judgment_amount=None), cfg, AS_OF).passed is False
