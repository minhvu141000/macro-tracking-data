#!/usr/bin/env python3
"""Build chart history for indicators NOT on FRED, from our own daily scrapes.

Some indicators the user wants to track (e.g. NAR Pending Home Sales) aren't on
FRED and have no free history API. But we already scrape their value into
data/raw/<date>.json every time they're released. This accumulates those values
into a time series the dashboard can chart — it starts with whatever is already
in the raw archive and grows by one point each time the indicator is published.

Output: data/scraped_history.json — same shape as a fred_history entry
        {id: {label, latest, previous, change_pct, history:[{date,value}]}}
so build_dashboard.build_history() can merge it next to the FRED series.

    python scripts/build_scraped_history.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT = ROOT / "data" / "scraped_history.json"

# pseudo_id → how to find its value in each raw file's releases.
# `match` is matched (case-insensitive) against release name; the FIRST release
# whose name matches AND has a numeric parsed.actual is used for that date.
SCRAPED_SERIES = {
    "PENDINGHOMES": {
        "label": "Pending Home Sales Index (NAR)",
        # the index LEVEL, not the MoM% — must contain "index"
        "match": r"pending home sales index",
    },
}


def _series_for(spec: dict, raw_files: list[Path]) -> list[dict]:
    pat = re.compile(spec["match"], re.I)
    seen: dict[str, float] = {}  # date → value (last write wins; dedupe per date)
    for f in raw_files:
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        date = d.get("date")
        if not date:
            continue
        for rel in d.get("releases", []):
            if not pat.search(rel.get("name", "")):
                continue
            val = (rel.get("parsed") or {}).get("actual")
            if isinstance(val, (int, float)):
                seen[date] = float(val)
                break
    return [{"date": dt, "value": v} for dt, v in sorted(seen.items())]


def build() -> dict:
    raw_files = sorted(RAW_DIR.glob("[0-9]*.json"))
    out = {}
    for pid, spec in SCRAPED_SERIES.items():
        hist = _series_for(spec, raw_files)
        if not hist:
            continue
        latest = hist[-1]
        prev = hist[-2] if len(hist) > 1 else None
        change = (round((latest["value"] - prev["value"]) / prev["value"] * 100, 3)
                  if prev and prev["value"] else None)
        out[pid] = {
            "label": spec["label"],
            "latest": latest,
            "previous": prev,
            "change_pct": change,
            "history": hist,
            "source": "scraped",
        }
    return out


def main() -> int:
    out = build()
    OUT.write_text(json.dumps({"schema_version": "1.0", "series": out}, indent=2, ensure_ascii=False))
    print(f"Wrote {OUT}")
    for pid, info in out.items():
        print(f"  {pid}: {len(info['history'])} điểm, mới nhất {info['latest']['date']}={info['latest']['value']}")
    if not out:
        print("  (chưa có điểm dữ liệu nào — sẽ tích lũy dần khi chỉ số được công bố)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
