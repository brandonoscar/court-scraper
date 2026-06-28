"""Turn a cached Tyler Odyssey detail page into a raw judgment dict.

IMPORTANT BOUNDARY: this does NOT modify the scraper. It *reuses* the scraper's
own ``CaseDetailParser`` (loaded by file path so we don't drag in Selenium) for
the fields it already extracts, and adds the two things the scraper ignores but
the screen needs: the financial assessment amount and the docket-event dates.

The screen reads the scraper's output; that is the only coupling.
"""
from __future__ import annotations

import importlib.util
import os
import re
from typing import List, Optional

from bs4 import BeautifulSoup

# --- load the scraper's parser without importing the odyssey package ---------
# (court_scraper.platforms.odyssey.__init__ imports Selenium, which the
#  screening layer must not depend on.)
_PARSER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "court_scraper", "platforms", "odyssey", "parsers", "case_detail.py",
)
_spec = importlib.util.spec_from_file_location("_odyssey_case_detail", _PARSER_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
CaseDetailParser = _mod.CaseDetailParser

_DATE_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")


def _financial_total(soup: BeautifulSoup) -> Optional[str]:
    """Return the 'Total Financial Assessment' string, or None if not captured.

    Returns None when the section is missing OR was still AJAX-loading when the
    page was scraped ('Loading financial, please wait...'). We do NOT guess.
    """
    body = soup.select_one("#divFinancialInformation_body")
    if not body:
        return None
    text = body.get_text("\n")
    m = re.search(r"Total Financial Assessment\s*\n\s*\$([0-9,]+\.\d{2})", text)
    return m.group(1) if m else None


def _event_dates(soup: BeautifulSoup) -> List[str]:
    """All MM/DD/YYYY dates appearing in the Events & Hearings section, sorted."""
    section = soup.select_one("#eventsInformationDiv")
    if not section:
        return []
    dates = sorted(set(_DATE_RE.findall(section.get_text(" "))))
    return dates


def _enforcement_events(soup: BeautifulSoup, keywords: List[str]) -> List[str]:
    """Dates of docket events whose text contains an enforcement keyword.

    Each event row in Odyssey starts with a date then a description; we scan
    line by line so a keyword only tags the date on its own line.
    """
    section = soup.select_one("#eventsInformationDiv")
    if not section:
        return []
    kws = [k.lower() for k in keywords]
    hits = []
    pending_date = None
    for raw in section.get_text("\n").splitlines():
        line = raw.strip()
        if not line:
            continue
        dm = _DATE_RE.search(line)
        if dm:
            pending_date = dm.group(1)
        low = line.lower()
        if pending_date and any(k in low for k in kws):
            hits.append(pending_date)
    return sorted(set(hits))


def extract_odyssey(html: str, enforcement_keywords: Optional[List[str]] = None) -> dict:
    """Parse one Odyssey detail page into a raw dict of screen-relevant fields."""
    soup = BeautifulSoup(html, "html.parser")
    parser = CaseDetailParser(html)

    # Fields the scraper's parser already knows how to read.
    try:
        case_number = parser.case_number
    except Exception:
        case_number = None
    try:
        case_type = parser.case_type
    except Exception:
        case_type = None
    try:
        court = parser.court
    except Exception:
        court = None
    try:
        file_date = parser.file_date
    except Exception:
        file_date = None
    parties = parser.parties or []
    dispositions = parser.disposition or []

    defendants = [p.get("party_name") for p in parties
                  if p.get("party_type") == "Defendant" and p.get("party_name")]
    plaintiffs = [p.get("party_name") for p in parties
                  if p.get("party_type") == "Plaintiff" and p.get("party_name")]

    # Prefer a real money judgment ("...for Plaintiff" / "Judgment"); fall back
    # to the most recent disposition so date_entered is still populated.
    judgment = _pick_judgment(dispositions)

    event_dates = _event_dates(soup)
    enf_dates = _enforcement_events(soup, enforcement_keywords or [])

    return {
        "case_number": case_number,
        "case_type": case_type,
        "court": court,
        "file_date": file_date,
        "defendants": defendants,
        "plaintiffs": plaintiffs,
        "judgment_date": judgment.get("judgment_date") if judgment else None,
        "judgment_type": judgment.get("judgment") if judgment else None,
        "judgment_amount": _financial_total(soup),
        "event_dates": event_dates,
        "last_activity_date": event_dates[-1] if event_dates else None,
        "last_enforcement_date": enf_dates[-1] if enf_dates else None,
    }


def _pick_judgment(dispositions: List[dict]) -> Optional[dict]:
    if not dispositions:
        return None
    for d in dispositions:
        text = (d.get("judgment") or "").lower()
        if d.get("judgment_for") == "Plaintiff" or "judgment" in text:
            return d
    return dispositions[-1]
