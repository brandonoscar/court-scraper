"""Ingest scraper output into the clean ``JudgmentRecord`` table.

Two documented input shapes, both being the scraper's *output* (we never call
the scraper or touch its fetching internals):

  1. --html-dir DIR   A directory of cached Tyler Odyssey detail pages, exactly
                      the format the scraper writes to
                      ~/.court-scraper/cache/<place_id>/<case>.html .
                      This is the path used for the REAL DeKalb run.

  2. --records FILE    A JSON-lines file of already-extracted records (one JSON
                      object per line). A generic path for non-Odyssey scraper
                      output and for the clearly-labeled SYNTHETIC sample set.
                      Set "is_synthetic": true on demo rows.
"""
from __future__ import annotations

import glob
import json
import os
from typing import List, Optional

from . import normalize as norm
from .extract import extract_odyssey
from .models import JudgmentRecord


def _record_from_raw(raw: dict, place_id: str, label: Optional[str],
                     source: str, is_synthetic: bool) -> JudgmentRecord:
    """Build a normalized JudgmentRecord from an extracted raw dict."""
    defendants = [norm.normalize_name(d) for d in raw.get("defendants", []) if d]
    plaintiffs = [norm.normalize_name(p) for p in raw.get("plaintiffs", []) if p]

    judgment_date = norm.parse_date(raw.get("judgment_date"))
    file_date = norm.parse_date(raw.get("file_date"))

    return JudgmentRecord(
        source_place_id=place_id,
        case_number=str(raw.get("case_number") or "").strip(),
        debtor_name=defendants[0] if defendants else None,
        debtor_names_all=defendants,
        creditor_name=plaintiffs[0] if plaintiffs else None,
        judgment_amount=norm.parse_amount(raw.get("judgment_amount")),
        judgment_date=judgment_date,
        date_entered=judgment_date or file_date,
        last_activity_date=norm.parse_date(raw.get("last_activity_date")),
        last_enforcement_date=norm.parse_date(raw.get("last_enforcement_date")),
        court=raw.get("court"),
        jurisdiction_label=label,
        case_type=raw.get("case_type"),
        judgment_type=raw.get("judgment_type"),
        raw_source=source,
        is_synthetic=is_synthetic,
    )


def ingest_html_dir(html_dir: str, place_id: str, label: Optional[str],
                    enforcement_keywords: List[str]) -> List[JudgmentRecord]:
    records = []
    for path in sorted(glob.glob(os.path.join(html_dir, "*.html"))):
        with open(path) as fh:
            html = fh.read()
        raw = extract_odyssey(html, enforcement_keywords=enforcement_keywords)
        if not raw.get("case_number"):
            continue
        records.append(_record_from_raw(
            raw, place_id, label, source=path, is_synthetic=False))
    return records


def ingest_records_file(records_path: str, place_id: str,
                        label: Optional[str]) -> List[JudgmentRecord]:
    records = []
    with open(records_path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            raw = json.loads(line)
            is_synth = bool(raw.get("is_synthetic", False))
            records.append(_record_from_raw(
                raw, raw.get("source_place_id", place_id), label,
                source=records_path, is_synthetic=is_synth))
    return records
