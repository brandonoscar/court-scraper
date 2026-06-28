# Screening layer — civil money judgments

A thin, **isolated** module that reads the `court-scraper`'s *output* and ranks
which money judgments are worth pursuing. It does **not** touch the scraper's
fetching internals — reading the scraper's output is the only coupling.

## The thesis it screens for

> "collectible debtor, dormant paper" — a money judgment is worth acquiring when
> it is **old**, shows **no recent enforcement activity**, and is **large
> enough** to pursue.

Current business thresholds (DeKalb County, GA / Tyler Odyssey):

- **No evictions** — dispossessory / unlawful-detainer case types are excluded.
- **Amount over $20,000.**
- **Age 8–15 years.**
- **Dormant** — no renewal/execution/garnishment in the last 5 years.

All of these live in [`config.yaml`](config.yaml). Change the screen by editing
config, never by editing rule code.

## Hard boundaries

- **No model decides eligibility.** Every qualification is an explicit, hard-coded
  comparison in [`rules.py`](rules.py). You can reproduce any verdict by hand.
  Models may *later* help with messy text extraction — never with whether a
  judgment qualifies.
- **No magic numbers.** Every threshold is a config value.
- **One county first.** Built and proven on `ga_dekalb`; generalize only after.

## Pipeline

```
scraper output ──► ingest ──► normalize ──► SQLite table ──► rules ──► ranked CSV
 (HTML / JSONL)                (judgments.db)            (auditable)   (worklist)
```

- **ingest** ([`ingest.py`](ingest.py)) — reads scraper output in two shapes:
  - `--html-dir DIR`: cached Tyler Odyssey detail pages (the format the scraper
    writes to `~/.court-scraper/cache/<place_id>/`). Extraction reuses the
    scraper's own `CaseDetailParser` read-only ([`extract.py`](extract.py)) and
    adds the financial amount + docket-event dates the scraper ignores.
  - `--records FILE`: a JSON-lines file of pre-extracted records (generic path;
    also used for the labeled synthetic sample).
- **normalize** ([`normalize.py`](normalize.py)) — parses dates, money, names.
- **store** ([`store.py`](store.py)) — SQLite. Why SQLite: one county, read-heavy,
  single analyst, zero ops; matches the scraper's own `cases.db`. Move to Postgres
  only if you later need concurrent writers or a shared service.
- **rules** ([`rules.py`](rules.py)) — one readable function per rule, each
  returning pass/fail **plus a plain-English reason quoting the actual numbers**.
- **screen** ([`screen.py`](screen.py)) — runs enabled rules, keeps records that
  pass them all, ranks by amount descending, writes the CSV with a `why_<rule>`
  column per rule.

## Run it

```bash
# 1. Ingest scraper output into the clean table
python -m screening.cli ingest --html-dir tests/fixtures/ga_dekalb        # real Odyssey pages
python -m screening.cli ingest --records sample_data/ga_dekalb_synthetic.jsonl  # labeled demo

# 2. Screen -> ranked worklist CSV
python -m screening.cli screen
# -> screening/out/worklist.csv

# tests
python -m pytest screening/tests/ -q
```

## Worklist output

`screening/out/worklist.csv`, one row per candidate, sorted by amount desc, with:
`rank, case_number, debtor_name, creditor_name, judgment_amount, date_entered,
judgment_type, jurisdiction, court, case_type, last_activity_date,
last_enforcement_date, is_synthetic, source`, plus a `why_<rule>` column for each
rule explaining exactly why the candidate passed.

## ⚠️ Real vs. synthetic data

This environment **cannot reach live court sites** — Wisconsin WCCA, Oklahoma
OSCN, and the Tyler Odyssey portals are all blocked by the egress policy (403 at
the proxy). So today's run uses two inputs:

1. **Real** already-scraped Odyssey pages in `tests/fixtures/ga_dekalb` — all
   evictions, so they correctly produce **0 candidates** under the current rules.
2. **Synthetic** [`sample_data/ga_dekalb_synthetic.jsonl`](../sample_data/ga_dekalb_synthetic.jsonl)
   — clearly labeled, `is_synthetic=1`, used only to exercise the rules at the
   10-candidate scale. **No row in it is a real judgment.**

To produce a real worklist of $20k+ dormant judgments, the scraper must run
against a live county (court domains allowlisted, or run locally and drop the
cached HTML / a records JSONL here), then re-run the two commands above.
