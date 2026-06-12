#!/usr/bin/env python3
"""Detect new releases in data/raw/ that are NOT in data/macro_theory.json.

Workflow:
1. Read macro_theory.json — collect all known short_name + full_name + aliases.
2. Scan all data/raw/*.json — extract unique release names.
3. Normalize names (strip "(May)" "(Apr)" "(Q1)" suffixes; strip "(MoM)" "(YoY)").
4. List names NOT matched to any indicator → these need to be added to theory.
5. By default, just PRINT missing list for review.
   With --list-only flag: print only names to stdout (for piping).
   With --auto-stub: append placeholder stubs to macro_theory.json (in a separate
   category "Cần bổ sung") so they show up in edu dashboard immediately.

Usage:
  python scripts/update_theory.py                      # show missing
  python scripts/update_theory.py --list-only          # names only
  python scripts/update_theory.py --auto-stub          # auto-add stubs
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THEORY_PATH = ROOT / "data" / "macro_theory.json"
RAW_DIR = ROOT / "data" / "raw"

# Skip noise: meta positioning, qualitative reports, speaker events, auctions (treated as one group)
SKIP_PATTERNS = [
    r"speaks",                # Fed speakers
    r"^cftc\s",               # CFTC positioning by asset (10+ daily)
    r"^opec crude oil production",  # by country
    r"opec monthly report",
    r"beige book",
    r"wasde report",
    r"\d+-(week|month|year) bill auction",
    r"\d+-year note auction",
    r"\d+-year tips",
]

# Manual aliases — short_name to release name patterns
EXTRA_ALIASES = {
    "NFP": ["nonfarm payrolls", "nonfarm payroll"],
    "Jobless Claims": ["initial jobless claims"],
    "ISM Mfg": ["ism manufacturing pmi"],
    "ISM Svc": ["ism non-manufacturing pmi", "ism services pmi"],
    "Michigan": ["michigan consumer sentiment"],
    "Consumer Conf": ["cb consumer confidence", "conference board consumer confidence"],
    "CPI": ["cpi (yoy)", "cpi (mom)", "cpi index"],
    "Core CPI": ["core cpi (yoy)", "core cpi (mom)", "core cpi index"],
    "PPI": ["ppi (yoy)", "ppi (mom)"],
    "Core PCE": ["core pce price index", "core pce prices"],
    "PCE": ["pce price index", "pce prices", "personal consumption expenditures"],
    "Existing Home Sales": ["existing home sales"],
    "Housing Starts": ["housing starts"],
    "Retail Sales": ["retail sales"],
    "GDP": ["gdp", "real gdp", "gross domestic product"],
    "AHE": ["average hourly earnings"],
    "JOLTS": ["jolts job openings", "job openings"],
    "Unemployment": ["unemployment rate"],
    "Fed Funds Rate": ["federal funds rate", "fomc"],
    "10Y Yield": ["10-year", "10y treasury"],
    "2Y Yield": ["2-year", "2y treasury"],
}


def normalize(name: str) -> str:
    """Lowercase + strip trailing parenthesized period/period like '(Jun)' '(Q1)' '(May)'."""
    n = name.lower().strip()
    # Strip date period suffix like " (May)" " (Apr)" " (Q1)" " (Jun 23)"
    n = re.sub(r"\s*\([a-z]{3,9}( \d{1,2})?\)\s*$", "", n)
    n = re.sub(r"\s*\(q[1-4]\)\s*$", "", n)
    # Strip MoM / YoY / WoW suffix
    n = re.sub(r"\s*\((mom|yoy|wow|qoq)\)\s*$", "", n)
    # Normalize whitespace
    n = re.sub(r"\s+", " ", n)
    return n.strip()


def should_skip(name: str) -> bool:
    n = name.lower()
    return any(re.search(p, n) for p in SKIP_PATTERNS)


def load_theory_aliases(theory: dict) -> set[str]:
    """Build set of normalized aliases that match known indicators."""
    aliases: set[str] = set()
    for cat in theory.get("categories", []):
        for ind in cat.get("indicators", []):
            for fld in ("short_name", "full_name"):
                v = ind.get(fld)
                if v:
                    aliases.add(normalize(v))
            # Also add release_aliases field if present (manual aliases)
            for a in ind.get("release_aliases", []) or []:
                aliases.add(normalize(a))
    # Apply EXTRA_ALIASES for hardcoded short_name → release pattern map
    for short, pats in EXTRA_ALIASES.items():
        if normalize(short) in aliases:
            for p in pats:
                aliases.add(normalize(p))
    return aliases


def collect_unique_releases() -> Counter:
    """Returns Counter of normalized release names across all raw files."""
    counts: Counter = Counter()
    for f in sorted(RAW_DIR.glob("*.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        for r in d.get("releases", []):
            nm = r.get("name", "").strip()
            if not nm:
                continue
            if should_skip(nm):
                continue
            counts[normalize(nm)] += 1
    return counts


def is_matched(rel_norm: str, aliases: set[str]) -> bool:
    """Check if a normalized release name matches any known indicator alias.
    Match logic:
    - exact match
    - alias is substring of release (e.g. 'cpi' matches 'cpi (mom)' already normalized to 'cpi')
    - release is substring of alias
    """
    if rel_norm in aliases:
        return True
    for a in aliases:
        if not a or len(a) < 3:
            continue
        if a in rel_norm or rel_norm in a:
            return True
    return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--list-only", action="store_true", help="Print missing names only, no headers")
    p.add_argument("--auto-stub", action="store_true",
                   help="Append placeholder stubs to macro_theory.json in category 'Cần bổ sung'")
    args = p.parse_args()

    if not THEORY_PATH.exists():
        print(f"theory file missing: {THEORY_PATH}", file=sys.stderr)
        return 1

    theory = json.loads(THEORY_PATH.read_text())
    aliases = load_theory_aliases(theory)
    counts = collect_unique_releases()

    missing = []
    for nm, cnt in counts.most_common():
        if not is_matched(nm, aliases):
            missing.append((nm, cnt))

    if args.list_only:
        for nm, _ in missing:
            print(nm)
        return 0

    print(f"Total unique releases (after skip filter): {len(counts)}")
    print(f"Theory aliases: {len(aliases)}")
    print(f"Missing from theory: {len(missing)}\n")
    for nm, cnt in missing[:50]:
        print(f"  [{cnt}] {nm}")
    if len(missing) > 50:
        print(f"  ... and {len(missing) - 50} more")

    if args.auto_stub and missing:
        # Find or create "Cần bổ sung" category
        cat = next((c for c in theory["categories"] if c.get("id") == "pending"), None)
        if not cat:
            cat = {"id": "pending", "name": "Cần Bổ Sung (Auto-detected)", "indicators": []}
            theory["categories"].append(cat)
        existing_ids = {i["id"] for i in cat["indicators"]}
        added = 0
        for nm, _ in missing:
            stub_id = re.sub(r"[^a-z0-9]+", "_", nm).strip("_").upper()[:40]
            if stub_id in existing_ids:
                continue
            cat["indicators"].append({
                "id": stub_id,
                "short_name": nm.title(),
                "full_name": nm.title(),
                "description": "(Cần bổ sung mô tả) — chỉ số này đã được phát hiện trong release data nhưng chưa có nội dung giáo dục.",
                "frequency": "—",
                "link": "",
                "expectation_meaning": "(Cần bổ sung)",
                "good_vs_bad": "(Cần bổ sung)",
                "market_reaction": "(Cần bổ sung)",
                "release_aliases": [nm],
            })
            existing_ids.add(stub_id)
            added += 1
        if added:
            THEORY_PATH.write_text(json.dumps(theory, indent=2, ensure_ascii=False))
            print(f"\nAdded {added} stub entries to category 'Cần Bổ Sung' in {THEORY_PATH}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
