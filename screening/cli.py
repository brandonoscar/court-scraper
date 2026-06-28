"""Command-line entry point for the screening layer.

    # 1. Ingest scraper output into the clean SQLite table
    python -m screening.cli ingest --html-dir tests/fixtures/ga_dekalb
    python -m screening.cli ingest --records sample_data/ga_dekalb_synthetic.jsonl

    # 2. Screen the table and write the ranked worklist CSV
    python -m screening.cli screen

All thresholds come from screening/config.yaml (override with --config).
"""
from __future__ import annotations

import argparse
import os

import yaml

from . import ingest as ingest_mod
from .screen import _as_of, screen, write_csv
from .store import JudgmentStore

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CONFIG = os.path.join(_HERE, "config.yaml")
_DEFAULT_DB = os.path.join(_HERE, "out", "judgments.db")


def load_config(path: str) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def cmd_ingest(args) -> None:
    config = load_config(args.config)
    place_id = config["jurisdiction"]["place_id"]
    label = config["jurisdiction"].get("label")
    enforcement = config["rules"]["dormancy"].get("enforcement_keywords", [])

    if args.html_dir:
        records = ingest_mod.ingest_html_dir(args.html_dir, place_id, label, enforcement)
        src = args.html_dir
    else:
        records = ingest_mod.ingest_records_file(args.records, place_id, label)
        src = args.records

    store = JudgmentStore(args.db)
    n = store.upsert(records)
    store.close()
    synth = sum(1 for r in records if r.is_synthetic)
    print(f"Ingested {n} record(s) from {src} into {args.db}"
          + (f"  ({synth} flagged SYNTHETIC)" if synth else ""))


def cmd_screen(args) -> None:
    config = load_config(args.config)
    if args.csv:
        config["output"]["csv_path"] = args.csv

    store = JudgmentStore(args.db)
    from .screen import _row_to_record
    records = [_row_to_record(r) for r in store.all_rows()]
    store.close()

    worklist = screen(records, config)
    csv_path = config["output"]["csv_path"]
    write_csv(worklist, csv_path)
    print(f"Screened {len(records)} judgment(s); {len(worklist)} candidate(s) "
          f"(as of {_as_of(config)}).")
    print(f"Worklist written to {csv_path}")
    for row in worklist[:10]:
        amt = row["judgment_amount"] or "?"
        flag = " [SYNTHETIC]" if row["is_synthetic"] else ""
        print(f"  #{row['rank']:>2}  ${amt:>12}  {row['debtor_name']}  "
              f"({row['case_number']}){flag}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="screening", description=__doc__)
    parser.add_argument("--config", default=_DEFAULT_CONFIG,
                        help="Path to config.yaml")
    parser.add_argument("--db", default=_DEFAULT_DB,
                        help="Path to the screening SQLite db")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ing = sub.add_parser("ingest", help="Ingest scraper output")
    grp = p_ing.add_mutually_exclusive_group(required=True)
    grp.add_argument("--html-dir", help="Directory of cached Odyssey detail HTML")
    grp.add_argument("--records", help="JSON-lines file of pre-extracted records")
    p_ing.set_defaults(func=cmd_ingest)

    p_scr = sub.add_parser("screen", help="Screen the table -> ranked CSV worklist")
    p_scr.add_argument("--csv", help="Override output CSV path")
    p_scr.set_defaults(func=cmd_screen)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
