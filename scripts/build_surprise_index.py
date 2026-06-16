#!/usr/bin/env python3
"""Build the Economic Surprise Index from all daily raw files.

A Citi-ESI-style gauge: are US data releases collectively beating or missing
consensus? Rolling sums of the per-day signed surprise scores (computed in
enrich_releases.day_surprise_score) on two axes:

  - GROWTH axis: positive = activity/labor data beating forecast → risk-on tailwind.
  - INFLATION axis: positive = prices hotter than forecast → hawkish pressure.

Deterministic, recomputed fresh each run by scanning data/raw/*.json (no
incremental state to drift). Writes:
  - data/surprise_index.json       full daily series (for dashboard charts)
  - the same file carries a compact `latest` block the analyst reads.

    python scripts/build_surprise_index.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT = ROOT / "data" / "surprise_index.json"

sys.path.insert(0, str(ROOT / "scripts"))
from enrich_releases import day_surprise_score  # noqa: E402


def _rolling_sum(series: list[dict], key: str, end: date, days: int) -> float:
    """Sum `key` over points within [end-days, end]."""
    lo = end.toordinal() - days
    total = 0.0
    for pt in series:
        d = date.fromisoformat(pt["date"]).toordinal()
        if lo < d <= end.toordinal():
            total += pt.get(key, 0.0) or 0.0
    return round(total, 2)


def build() -> dict:
    files = sorted(RAW_DIR.glob("*.json"))
    series: list[dict] = []
    for f in files:
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        d = data.get("date") or f.stem
        # Prefer the pre-computed score; recompute from releases for older files.
        score = (data.get("release_summary") or {}).get("day_surprise_score")
        if not score:
            score = day_surprise_score(data.get("releases", []))
        # Only keep days that actually had scored releases on an axis
        if score.get("n_growth") or score.get("n_inflation"):
            series.append({
                "date": d,
                "growth_score": score.get("growth_score", 0.0),
                "inflation_score": score.get("inflation_score", 0.0),
            })

    series.sort(key=lambda x: x["date"])
    latest: dict = {}
    if series:
        end = date.fromisoformat(series[-1]["date"])
        g1 = _rolling_sum(series, "growth_score", end, 30)
        g3 = _rolling_sum(series, "growth_score", end, 90)
        i1 = _rolling_sum(series, "inflation_score", end, 30)
        i3 = _rolling_sum(series, "inflation_score", end, 90)
        # Trend: last 30d vs the 30d before it
        prev_end = date.fromordinal(end.toordinal() - 30)
        g_prev = _rolling_sum(series, "growth_score", prev_end, 30)
        g_trend = "rising" if g1 > g_prev else ("falling" if g1 < g_prev else "flat")

        def lab(v: float) -> str:
            if v > 2:
                return "beating mạnh"
            if v > 0.5:
                return "beating nhẹ"
            if v < -2:
                return "missing mạnh"
            if v < -0.5:
                return "missing nhẹ"
            return "đúng kỳ vọng"

        latest = {
            "as_of": series[-1]["date"],
            "growth_1m": g1, "growth_3m": g3,
            "inflation_1m": i1, "inflation_3m": i3,
            "growth_trend_1m": g_trend,
            "note": (
                f"Growth surprise 1M {g1:+.1f} ({lab(g1)}, {g_trend}), 3M {g3:+.1f}. "
                f"Inflation surprise 1M {i1:+.1f} ({lab(i1)}). "
                + ("Data đang vượt kỳ vọng → risk-on tailwind." if g1 > 0.5 else
                   "Data đang hụt kỳ vọng → growth scare risk." if g1 < -0.5 else
                   "Data sát kỳ vọng → ít động lực bất ngờ.")
            ),
        }

    return {"updated_at": date.today().isoformat(), "latest": latest, "series": series}


def main() -> int:
    payload = build()
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Wrote {OUT} — {len(payload['series'])} scored days")
    if payload["latest"]:
        print("  " + payload["latest"]["note"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
