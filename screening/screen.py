"""Run the rules over the stored judgments and emit a ranked CSV worklist.

A candidate is any judgment that passes every *enabled* rule (when
output.require_all_rules is true). The worklist is sorted by amount descending,
one row per candidate, with the screen-relevant fields plus a `why_<rule>`
column quoting exactly why each rule passed -- so any flag is auditable.
"""
from __future__ import annotations

import csv
import os
from datetime import date, datetime
from typing import List

from .models import JudgmentRecord
from .rules import RULES, RuleResult


def _row_to_record(row) -> JudgmentRecord:
    def d(v):
        return datetime.strptime(v, "%Y-%m-%d").date() if v else None
    return JudgmentRecord(
        source_place_id=row["source_place_id"],
        case_number=row["case_number"],
        debtor_name=row["debtor_name"],
        debtor_names_all=(row["debtor_names_all"] or "").split("; ") if row["debtor_names_all"] else [],
        creditor_name=row["creditor_name"],
        judgment_amount=float(row["judgment_amount"]) if row["judgment_amount"] else None,
        judgment_date=d(row["judgment_date"]),
        date_entered=d(row["date_entered"]),
        last_activity_date=d(row["last_activity_date"]),
        last_enforcement_date=d(row["last_enforcement_date"]),
        judgment_for=row["judgment_for"],
        satisfaction_date=d(row["satisfaction_date"]),
        court=row["court"],
        jurisdiction_label=row["jurisdiction_label"],
        case_type=row["case_type"],
        judgment_type=row["judgment_type"],
        raw_source=row["raw_source"],
        is_synthetic=bool(int(row["is_synthetic"])) if row["is_synthetic"] else False,
    )


def evaluate(record: JudgmentRecord, config: dict, as_of: date) -> List[RuleResult]:
    """Run every enabled rule against one record."""
    rules_cfg = config["rules"]
    results = []
    for name, fn in RULES:
        cfg = rules_cfg.get(name, {})
        if not cfg.get("enabled", False):
            continue
        results.append(fn(record, cfg, as_of))
    return results


def screen(records: List[JudgmentRecord], config: dict) -> List[dict]:
    """Return the ranked worklist (list of CSV-ready dicts) for the candidates."""
    as_of = _as_of(config)
    require_all = config["output"].get("require_all_rules", True)

    candidates = []
    for rec in records:
        results = evaluate(rec, config, as_of)
        passed_all = all(r.passed for r in results)
        if require_all and not passed_all:
            continue
        candidates.append((rec, results))

    # Rank by amount descending; unknown amounts sort last.
    candidates.sort(key=lambda c: (c[0].judgment_amount or -1), reverse=True)

    worklist = []
    for rank, (rec, results) in enumerate(candidates, start=1):
        row = {
            "rank": rank,
            "case_number": rec.case_number,
            "debtor_name": rec.debtor_name,
            "creditor_name": rec.creditor_name,
            "judgment_amount": f"{rec.judgment_amount:.2f}" if rec.judgment_amount is not None else "",
            "date_entered": rec.date_entered.isoformat() if rec.date_entered else "",
            "judgment_for": rec.judgment_for or "",
            "judgment_type": rec.judgment_type or "",
            "satisfaction_date": rec.satisfaction_date.isoformat() if rec.satisfaction_date else "",
            "jurisdiction": rec.jurisdiction_label or rec.source_place_id,
            "court": rec.court or "",
            "case_type": rec.case_type or "",
            "last_activity_date": rec.last_activity_date.isoformat() if rec.last_activity_date else "",
            "last_enforcement_date": rec.last_enforcement_date.isoformat() if rec.last_enforcement_date else "",
            "is_synthetic": int(rec.is_synthetic),
            "source": rec.raw_source or "",
        }
        for r in results:
            row[f"why_{r.name}"] = r.reason
        worklist.append(row)
    return worklist


def write_csv(worklist: List[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not worklist:
        # Still write a header-only file so downstream tooling has a stable shape.
        fieldnames = ["rank", "case_number", "debtor_name", "creditor_name",
                      "judgment_amount", "date_entered", "judgment_for",
                      "judgment_type", "satisfaction_date", "jurisdiction",
                      "court", "case_type", "last_activity_date",
                      "last_enforcement_date", "is_synthetic", "source"]
    else:
        fieldnames = list(worklist[0].keys())
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(worklist)


def _as_of(config: dict) -> date:
    raw = config.get("as_of_date")
    if not raw:
        return date.today()
    if isinstance(raw, date):
        return raw
    return datetime.strptime(str(raw), "%Y-%m-%d").date()
