"""The screening rules.

ABSOLUTE BOUNDARY: every qualification decision in here is an explicit,
hard-coded comparison against a config value. No model, no heuristic guess, no
fuzzy judgment about whether a judgment "looks" collectible. You can read each
function top to bottom and reproduce its verdict by hand. That is the point.

Each rule is a separate function with the same shape:

    rule_<name>(record, cfg, as_of) -> RuleResult

and explains *why* it passed or failed in plain English, quoting the actual
numbers so a flagged judgment is fully traceable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from .models import JudgmentRecord


@dataclass
class RuleResult:
    name: str
    passed: bool
    reason: str


def _years_between(earlier: Optional[date], later: date) -> Optional[float]:
    if earlier is None:
        return None
    return (later - earlier).days / 365.25


# ---------------------------------------------------------------------------
# Rule 0 -- exclude case types we never pursue (e.g. evictions)
# ---------------------------------------------------------------------------
def rule_case_type_exclude(record: JudgmentRecord, cfg: dict, as_of: date) -> RuleResult:
    name = "case_type_exclude"
    keywords = [k.lower() for k in cfg.get("exclude_keywords", [])]
    case_type = (record.case_type or "")
    low = case_type.lower()
    for kw in keywords:
        if kw in low:
            return RuleResult(name, False,
                              f"excluded case type: '{case_type}' matches "
                              f"'{kw}'")
    shown = case_type if case_type else "(unspecified)"
    return RuleResult(name, True, f"case type '{shown}' is not on the exclude list")


# ---------------------------------------------------------------------------
# Rule 1 -- judgment age inside the target band
# ---------------------------------------------------------------------------
def rule_judgment_age(record: JudgmentRecord, cfg: dict, as_of: date) -> RuleResult:
    name = "judgment_age"
    min_y, max_y = cfg["min_years"], cfg["max_years"]
    entered = record.date_entered
    age = _years_between(entered, as_of)
    if age is None:
        return RuleResult(name, False, "no judgment/entry date available to age")
    if age < min_y:
        return RuleResult(name, False,
                          f"too recent: {age:.1f}y old < {min_y}y minimum "
                          f"(entered {entered})")
    if age > max_y:
        return RuleResult(name, False,
                          f"too old: {age:.1f}y old > {max_y}y maximum "
                          f"(entered {entered})")
    return RuleResult(name, True,
                      f"age {age:.1f}y is within {min_y}-{max_y}y band "
                      f"(entered {entered})")


# ---------------------------------------------------------------------------
# Rule 2 -- dormant: no enforcement activity within the inactive window
# ---------------------------------------------------------------------------
def rule_dormancy(record: JudgmentRecord, cfg: dict, as_of: date) -> RuleResult:
    name = "dormancy"
    inactive_years = cfg["inactive_years"]
    last_enf = record.last_enforcement_date
    if last_enf is None:
        return RuleResult(name, True,
                          "dormant: no enforcement event "
                          "(renewal/execution/garnishment) ever recorded")
    years_since = _years_between(last_enf, as_of)
    if years_since >= inactive_years:
        return RuleResult(name, True,
                          f"dormant: last enforcement event {last_enf} is "
                          f"{years_since:.1f}y ago (>= {inactive_years}y cutoff)")
    return RuleResult(name, False,
                      f"active: enforcement event {last_enf} was "
                      f"{years_since:.1f}y ago (< {inactive_years}y cutoff)")


# ---------------------------------------------------------------------------
# Rule 3 -- judgment amount clears the floor
# ---------------------------------------------------------------------------
def rule_amount_floor(record: JudgmentRecord, cfg: dict, as_of: date) -> RuleResult:
    name = "amount_floor"
    floor = cfg["min_amount"]
    amt = record.judgment_amount
    if amt is None:
        return RuleResult(name, False,
                          "amount unknown (not captured in scraped page)")
    if amt < floor:
        return RuleResult(name, False,
                          f"amount ${amt:,.2f} < ${floor:,.2f} floor")
    return RuleResult(name, True,
                      f"amount ${amt:,.2f} >= ${floor:,.2f} floor")


# Registry: rule name -> function. Disabled rules (per config) are skipped.
RULES = [
    ("case_type_exclude", rule_case_type_exclude),
    ("judgment_age", rule_judgment_age),
    ("dormancy", rule_dormancy),
    ("amount_floor", rule_amount_floor),
]
