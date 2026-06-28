"""The clean, normalized record the screen operates on.

One ``JudgmentRecord`` == one money judgment we might screen. Every field here
is something a rule reads or the worklist reports. Keeping it a plain dataclass
(no ORM) keeps the screening layer decoupled from the scraper's database.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import List, Optional


@dataclass
class JudgmentRecord:
    # --- identity -----------------------------------------------------------
    source_place_id: str
    case_number: str

    # --- parties ------------------------------------------------------------
    debtor_name: Optional[str] = None          # primary defendant
    debtor_names_all: List[str] = field(default_factory=list)
    creditor_name: Optional[str] = None         # primary plaintiff

    # --- the money ----------------------------------------------------------
    judgment_amount: Optional[float] = None     # None == not captured / unknown

    # --- dates (all stored ISO YYYY-MM-DD) ----------------------------------
    judgment_date: Optional[date] = None        # date judgment was entered
    date_entered: Optional[date] = None         # judgment_date, else filing date
    last_activity_date: Optional[date] = None    # most recent docket event of any kind
    last_enforcement_date: Optional[date] = None  # most recent enforcement-type event

    # --- jurisdiction / context --------------------------------------------
    court: Optional[str] = None
    jurisdiction_label: Optional[str] = None
    case_type: Optional[str] = None
    judgment_type: Optional[str] = None         # e.g. "Order and Judgment"

    # --- provenance / honesty ----------------------------------------------
    raw_source: Optional[str] = None            # file path or record id it came from
    is_synthetic: bool = False                  # True == demo data, NOT a real record

    def to_row(self) -> dict:
        """Flatten to a dict of primitives suitable for SQLite / CSV."""
        d = asdict(self)
        d["debtor_names_all"] = "; ".join(self.debtor_names_all)
        for k in ("judgment_date", "date_entered", "last_activity_date",
                  "last_enforcement_date"):
            d[k] = d[k].isoformat() if d[k] else None
        d["is_synthetic"] = int(self.is_synthetic)
        return d
