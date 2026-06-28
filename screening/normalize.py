"""Field normalization helpers.

Pure, dependency-free functions that turn the scraper's raw strings into the
typed values the rules compare against. No screening *decision* happens here --
this layer only cleans and parses.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

# Date formats seen in Tyler Odyssey pages (and common variants).
_DATE_FORMATS = ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y")


def parse_date(value) -> Optional[date]:
    """Parse a date string into a ``date``; return None if unparseable."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_amount(value) -> Optional[float]:
    """Parse a money string like '$1,903.00' or '(124.00)' into a float.

    Parentheses are treated as the accounting-negative convention but the
    magnitude is what we keep (an assessment of $124 is a $124 obligation).
    Returns None if no numeric amount is present.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    s = s.replace(",", "").replace("$", "").replace("(", "").replace(")", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return abs(float(m.group())) if m else None


def normalize_name(value) -> Optional[str]:
    """Collapse whitespace in a party name; leave casing as-is for traceability."""
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None
