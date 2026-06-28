#!/usr/bin/env python3
"""Standalone OSCN (Oklahoma) harvester -- RUN THIS ON YOUR OWN MACHINE.

Why a separate script: the Claude session that built the screening layer runs in
a sandbox whose network egress is blocked, so it cannot fetch court sites. This
script has no such restriction. Run it where the internet works; it writes a
records file that the screening layer ingests verbatim.

It is intentionally self-contained -- only `requests` and `beautifulsoup4` --
so you don't need the rest of court-scraper installed:

    pip install requests beautifulsoup4
    python screening/harvest_oscn.py --county tulsa --year 2014 --start 1 --end 1500
    # -> writes sample_data/oscn_tulsa_records.jsonl  (+ raw HTML cache)

Then back in the screening repo:

    python -m screening.cli ingest --records sample_data/oscn_tulsa_records.jsonl
    python -m screening.cli screen

It targets CJ cases ("Civil relief more than $10,000"), which is where real
money judgments live. Evictions in OK are a different case type (FED) and are
naturally excluded. Be a good citizen: the default request delay is 1s.

NOTE ON AMOUNTS: judgment-amount text on OSCN varies case to case. This script
captures the dollar figure(s) found in JUDGMENT docket rows (best-effort) and
also keeps the raw judgment docket text in the record so every amount is
auditable. If amounts look off on real judgment cases, send a couple of the
cached HTML files back and the extractor can be tuned against them.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time

import requests
from bs4 import BeautifulSoup

BASE = "https://www.oscn.net/dockets/GetCaseInformation.aspx"
ROLE_RE = re.compile(
    r"(Plaintiff|Defendant|Garnishee|Petitioner|Respondent|Third Party)", re.I)

# Docket text that signals the judgment itself.
JUDGMENT_MARKERS = ["JUDGMENT", "JOURNAL ENTRY OF JUDGMENT", "DEFAULT JUDGMENT"]
# Docket text that signals someone is actively enforcing/renewing (resets dormancy).
ENFORCEMENT_MARKERS = [
    "GARNISH", "EXECUTION", "REVIVOR", "REVIVAL", "RENEWAL", "LEVY",
    "CITATION", "ASSET HEARING", "HEARING ON ASSETS", "WRIT",
]


def parse_case(html: str, county: str, case_number: str) -> dict | None:
    """Parse one OSCN GetCaseInformation page into a screening record.

    Returns None if the page is not a real case (gap in numbering, error page).
    """
    soup = BeautifulSoup(html, "html.parser")
    h2 = soup.find("h2", class_="styletop")
    if not h2:
        return None
    header_tbl = h2.find_next("table")
    if not header_tbl:
        return None
    cell = header_tbl.find_all("tr")[0].find_all("td")[-1]
    cell_text = re.sub(r"\s+", " ", cell.get_text(" ", strip=True))

    # Case type is the parenthetical in the header strong text.
    m_type = re.search(r"\(([^)]*)\)", cell_text)
    case_type = m_type.group(1).strip() if m_type else None
    m_filed = re.search(r"Filed:\s*(\d{1,2}/\d{1,2}/\d{4})", cell_text)
    file_date = m_filed.group(1) if m_filed else None

    plaintiffs, defendants = _parse_parties(soup)
    docket = _parse_docket(soup)
    dispositions = _parse_disposition(soup)

    # A real money judgment is signalled two ways; require JUDGMENT and not a
    # dismissal so dismissed/closed cases don't get mistaken for judgments.
    def _is_judgment(text: str) -> bool:
        u = text.upper()
        return any(k in u for k in JUDGMENT_MARKERS) and "DISMISS" not in u

    judgment_dispositions = [d for d in dispositions if _is_judgment(d["text"])]
    judgment_rows = [d for d in docket if _is_judgment(d["description"])]
    enforcement_rows = [d for d in docket
                        if any(k in (d["code"] + " " + d["description"]).upper()
                               for k in ENFORCEMENT_MARKERS)]

    if judgment_dispositions:
        judgment_date = judgment_dispositions[-1]["date"]
        judgment_text = judgment_dispositions[-1]["text"]
    elif judgment_rows:
        judgment_date = judgment_rows[-1]["date"]
        judgment_text = judgment_rows[-1]["description"]
    else:
        judgment_date = judgment_text = None

    # Amount: prefer judgment docket rows (Amount column); fall back to any
    # dollar figure in the judgment disposition text.
    judgment_amount = _best_amount(judgment_rows)
    if judgment_amount is None and judgment_dispositions:
        judgment_amount = _best_amount(
            [{"description": d["text"], "amount": ""} for d in judgment_dispositions])

    last_activity = docket[-1]["date"] if docket else None
    last_enforcement = enforcement_rows[-1]["date"] if enforcement_rows else None

    return {
        "is_synthetic": False,
        "source_place_id": f"ok_{county.lower()}",
        "case_number": case_number,
        "case_type": case_type,
        "court": f"District Court of {county.title()} County, OK",
        "file_date": file_date,
        "plaintiffs": plaintiffs,
        "defendants": defendants,
        "judgment_date": judgment_date,
        "judgment_type": judgment_text,
        "judgment_amount": judgment_amount,
        "last_activity_date": last_activity,
        "last_enforcement_date": last_enforcement,
        # kept for auditability of the best-effort amount:
        "judgment_docket_text": judgment_text,
    }


def _clean(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


def _parse_parties(soup) -> tuple[list[str], list[str]]:
    plaintiffs, defendants = [], []

    # Preferred: 2026 OSCN template uses structured span.parties_party blocks.
    blocks = soup.select("span.parties_party")
    if blocks:
        for blk in blocks:
            name_el = blk.select_one(".parties_partyname")
            type_el = blk.select_one(".parties_type")
            if not name_el or not type_el:
                continue
            name = _clean(name_el.get_text()).rstrip(",").strip()
            role = _clean(type_el.get_text()).lower()
            if not name:
                continue
            if role == "plaintiff":
                plaintiffs.append(name)
            elif role == "defendant":
                defendants.append(name)
        return plaintiffs, defendants

    # Fallback: older template -- plain text after the "Parties" header.
    header = soup.find(lambda t: t.name in ("h2", "h3")
                       and t.get_text(strip=True) == "Parties")
    if not header:
        return plaintiffs, defendants
    block = header.find_next_sibling()
    if not block:
        return plaintiffs, defendants
    for chunk in block.get_text(" | ", strip=True).split("|"):
        m = ROLE_RE.search(chunk)
        if not m:
            continue
        role = m.group(1).lower()
        name = _clean(chunk[:m.start()]).rstrip(",").strip()
        if not name:
            continue
        if role == "plaintiff":
            plaintiffs.append(name)
        elif role == "defendant":
            defendants.append(name)
    return plaintiffs, defendants


def _parse_disposition(soup) -> list[dict]:
    """Read the structured Disposition tables (each issue's outcome + date)."""
    out = []
    for tbl in soup.select("table.Disposition"):
        for cell in tbl.select("td.countdisposition"):
            text = _clean(cell.get_text())
            if not text:
                continue
            m = re.search(r"Disposed:\s*(.*?),?\s*(\d{1,2}/\d{1,2}/\d{4})", text)
            if m:
                out.append({"text": _clean(m.group(1)), "date": m.group(2)})
            else:
                out.append({"text": text, "date": None})
    return out


def _parse_docket(soup) -> list[dict]:
    header = soup.find(lambda t: t.name in ("h2", "h3")
                       and t.get_text(strip=True) == "Docket")
    rows = []
    if not header:
        return rows
    table = header.find_next("table")
    if not table:
        return rows
    for tr in table.find_all("tr"):
        cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True))
                 for c in tr.find_all("td")]
        if len(cells) < 3:
            continue
        date = _norm_date(cells[0])
        if not date:
            continue  # skips the header row and continuation rows
        # The 2026 template adds a 6th "Amount" column; older pages have none.
        amount = cells[5] if len(cells) >= 6 else (cells[-1] if len(cells) > 3 else "")
        rows.append({"date": date, "code": cells[1],
                     "description": cells[2] if len(cells) > 2 else "",
                     "amount": amount})
    return rows


def _clean_amount(text: str) -> float | None:
    m = re.search(r"\$\s?([\d,]+\.\d{2})", text or "")
    return float(m.group(1).replace(",", "")) if m else None


def _best_amount(rows: list[dict]) -> str | None:
    """Largest dollar figure tied to a judgment row -- from the Amount column
    first, then any amount written inline in the description."""
    amounts = []
    for r in rows:
        amt = _clean_amount(r.get("amount", ""))
        if amt is not None:
            amounts.append(amt)
        for m in re.findall(r"\$\s?[\d,]+\.\d{2}", r.get("description", "")):
            amounts.append(float(m.replace("$", "").replace(",", "").strip()))
    if not amounts:
        return None
    return f"${max(amounts):,.2f}"


def _norm_date(s: str) -> str | None:
    m = re.match(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", s.strip())
    if not m:
        return None
    mm, dd, yyyy = m.groups()
    return f"{int(mm):02d}/{int(dd):02d}/{yyyy}"


def fetch(session, county: str, case_number: str, cache_dir: str):
    """Return (html, hit_network). hit_network is False on a cache hit.

    The caller paces on hit_network so we never burst the server, and so cache
    hits (no request) don't waste the delay.
    """
    cache_path = os.path.join(cache_dir, f"{case_number}.html")
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as fh:
            return fh.read(), False
    resp = session.get(BASE, params={"db": county, "number": case_number},
                       timeout=30)
    if resp.status_code != 200:
        return None, True
    os.makedirs(cache_dir, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as fh:
        fh.write(resp.text)
    return resp.text, True


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--county", default="tulsa", help="OSCN db, e.g. tulsa, oklahoma")
    ap.add_argument("--prefix", default="CJ", help="Case-type prefix (CJ = civil >$10k)")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--start", type=int, default=1, help="First sequence number")
    ap.add_argument("--end", type=int, required=True, help="Last sequence number")
    ap.add_argument("--out", default="sample_data/oscn_tulsa_records.jsonl")
    ap.add_argument("--cache-dir", default="sample_data/oscn_cache")
    ap.add_argument("--delay", type=float, default=1.0, help="Seconds between requests")
    ap.add_argument("--only-judgments", action="store_true",
                    help="Only write records that have a judgment docket entry")
    ap.add_argument("--limit", type=int, default=0,
                    help="Stop after writing this many records (0 = no limit). "
                         "Use to grab just enough cases fast.")
    args = ap.parse_args(argv)

    session = requests.Session()
    session.headers["User-Agent"] = "court-scraper screening harvester (research)"
    cache_dir = os.path.join(args.cache_dir, f"{args.county}")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    written = found = consecutive_blocks = 0
    with open(args.out, "w", encoding="utf-8") as out:
        for seq in range(args.start, args.end + 1):
            case_number = f"{args.prefix}-{args.year}-{seq}"
            try:
                html, hit_network = fetch(session, args.county, case_number, cache_dir)
            except requests.RequestException as e:
                print(f"  {case_number}: request error {e}")
                time.sleep(args.delay)
                continue
            # Pace EVERY network request -- not just ones that yield a judgment --
            # so non-judgment pages don't get fetched back-to-back and trip a ban.
            if hit_network:
                time.sleep(args.delay)
            # Back off and stop if OSCN appears to be blocking us (repeated non-200s),
            # rather than hammering through a rate-limit. Resume after the reset.
            if hit_network and html is None:
                consecutive_blocks += 1
                if consecutive_blocks >= 5:
                    print(f"  {case_number}: {consecutive_blocks} blocked requests "
                          "in a row -- stopping to respect the rate limit. "
                          "Resume later (cached pages are kept).")
                    break
                continue
            consecutive_blocks = 0
            if not html:
                continue
            rec = parse_case(html, args.county, case_number)
            if not rec:
                continue
            found += 1
            if args.only_judgments and not rec.get("judgment_date"):
                continue
            out.write(json.dumps(rec) + "\n")
            out.flush()
            written += 1
            amt = rec.get("judgment_amount") or "-"
            print(f"  {case_number}: {rec['case_type']} | amt {amt} | "
                  f"def {rec['defendants'][:1]}")
            if args.limit and written >= args.limit:
                print(f"  reached --limit {args.limit}, stopping.")
                break

    print(f"\nFound {found} real case(s); wrote {written} record(s) to {args.out}")
    print(f"Raw HTML cached under {cache_dir}")
    print("Next: python -m screening.cli ingest --records " + args.out)


if __name__ == "__main__":
    main()
