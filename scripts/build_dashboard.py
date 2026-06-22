#!/usr/bin/env python3
"""Build dashboard/data.js from collected raw data + daily reports.

Reads data/raw/*.json and data/daily/*.md, emits a single JS file
that the static dashboard HTML loads.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DAILY_DIR = ROOT / "data" / "daily"
MONTHLY_DIR = ROOT / "data" / "monthly"
SECTORS_FILE = ROOT / "data" / "sectors_latest.json"
CROSS_ASSET_FILE = ROOT / "data" / "cross_asset_latest.json"
CALENDAR_FILE = ROOT / "data" / "calendar_latest.json"
THEORY_FILE = ROOT / "data" / "macro_theory.json"
WEEKLY_DIR = ROOT / "data" / "weekly"
OUT = ROOT / "dashboard" / "data.js"


def load_raw_files() -> list[dict[str, Any]]:
    files = sorted(RAW_DIR.glob("*.json"))
    out = []
    for f in files:
        try:
            out.append(json.loads(f.read_text()))
        except Exception as exc:
            print(f"  Skipping {f}: {exc}")
    return out


def parse_daily_front_matter(path: Path, include_full_body: bool = False) -> dict[str, Any]:
    text = path.read_text()
    fm: dict[str, Any] = {"file": path.name, "date": path.stem}
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        fm["body_preview"] = text[:500]
        if include_full_body:
            fm["body"] = text
        return fm
    block, body = m.group(1), m.group(2)
    for line in block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip("\"'")
    body = body.strip()
    fm["body_preview"] = body.split("\n\n", 1)[0][:500]
    if include_full_body:
        fm["body"] = body
    return fm


def _merge_extra_history(history: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Merge non-FRED series (scraped accumulator + EIA) so the dashboard charts
    them alongside FRED. Each file holds {series: {id: {label,latest,...,history}}}.
    """
    for fname in ("scraped_history.json", "eia_history.json", "fed_forecasts_history.json"):
        p = ROOT / "data" / fname
        if not p.exists():
            continue
        try:
            for sid, info in (json.loads(p.read_text()).get("series", {}) or {}).items():
                if isinstance(info, dict) and info.get("history"):
                    history[sid] = info
        except Exception as exc:
            print(f"  {fname} merge failed: {exc}")
    return history


def build_history(raw_files: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """For each FRED series, build a flat time series.

    Source of truth (in priority order):
    1. data/fred_history.json (full 10y history, updated daily by collect.py)
    2. Latest raw file's fred_snapshot.history (fallback if history file missing).

    The dedicated history file lets daily raw JSON files stay small (~20 obs each)
    for LLM token efficiency, while dashboard charts still show full history.
    """
    history: dict[str, dict[str, Any]] = {}

    # Preferred source: dedicated history file
    hist_path = ROOT / "data" / "fred_history.json"
    if hist_path.exists():
        try:
            hist_data = json.loads(hist_path.read_text())
            snapshot = hist_data.get("fred_snapshot", {})
            for sid, info in snapshot.items():
                if not isinstance(info, dict):
                    continue
                history[sid] = {
                    "label": info.get("label", sid),
                    "latest": info.get("latest"),
                    "previous": info.get("previous"),
                    "change_pct": info.get("change_pct"),
                    "history": info.get("history", []),
                }
            return _merge_extra_history(history)
        except Exception as exc:
            print(f"  fred_history.json failed: {exc} — falling back to raw files")

    # Fallback: use latest raw file
    if not raw_files:
        return history
    latest = raw_files[-1].get("fred_snapshot", {}) or {}
    for sid, info in latest.items():
        if not isinstance(info, dict):
            continue
        history[sid] = {
            "label": info.get("label", sid),
            "latest": info.get("latest"),
            "previous": info.get("previous"),
            "change_pct": info.get("change_pct"),
            "history": info.get("history", []),
        }
    return _merge_extra_history(history)


def build_today_releases(raw_files: list[dict[str, Any]]) -> dict[str, Any]:
    if not raw_files:
        return {"date": None, "releases": []}
    latest = raw_files[-1]
    # Pass through enriched blocks so the dashboard can surface the day's
    # surprise_count + hard-data inflation context, not just raw rows.
    return {
        "date": latest.get("date"),
        "releases": latest.get("releases", []),
        "release_summary": latest.get("release_summary", {}),
        "inflation_context": latest.get("inflation_context", {}),
    }


def build_releases_history(raw_files: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    history = {}
    for r in raw_files:
        date = r.get("date")
        if date:
            history[date] = r.get("releases", [])
    return history



def build() -> None:
    raw_files = load_raw_files()
    daily_files = sorted(DAILY_DIR.glob("*.md"))
    # Chỉ giữ báo cáo tháng dạng YYYY-MM.md — loại scorecard.md, rotation_engine_scorecard.md...
    monthly_files = sorted(f for f in MONTHLY_DIR.glob("*.md") if re.fullmatch(r"\d{4}-\d{2}", f.stem))

    daily_reports = [parse_daily_front_matter(f, include_full_body=True) for f in daily_files]
    monthly_reports = [parse_daily_front_matter(f, include_full_body=True) for f in monthly_files]

    # Latest daily + monthly with FULL body for inline rendering
    latest_daily = parse_daily_front_matter(daily_files[-1], include_full_body=True) if daily_files else None
    latest_monthly = parse_daily_front_matter(monthly_files[-1], include_full_body=True) if monthly_files else None

    def _load(p, label):
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text())
        except Exception as exc:
            print(f"  Skipping {label}: {exc}")
            return {}

    rotation_forecast = _load(ROOT / "data" / "monthly_rotation_forecast_latest.json", "rotation_forecast")
    sectors_payload = _load(SECTORS_FILE, "sectors")
    cross_asset_payload = _load(CROSS_ASSET_FILE, "cross_asset")
    calendar_payload = _load(CALENDAR_FILE, "calendar")
    theory_payload = _load(THEORY_FILE, "theory")
    fred_history_payload = _load(ROOT / "data" / "fred_history.json", "fred_history")

    weekly_dated = sorted(
        [f for f in WEEKLY_DIR.glob("*.md") if f.name != "current.md"]
    ) if WEEKLY_DIR.exists() else []
    weekly_reports = [parse_daily_front_matter(f, include_full_body=True) for f in weekly_dated]
    latest_weekly = parse_daily_front_matter(weekly_dated[-1], include_full_body=True) \
        if weekly_dated else None

    payload = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "daily_releases": build_today_releases(raw_files),
        "releases_history": build_releases_history(raw_files),
        "history": build_history(raw_files),
        "daily_reports": daily_reports,
        "monthly_reports": monthly_reports,
        "weekly_reports": weekly_reports,
        "raw_dates": [r.get("date") for r in raw_files if r.get("date")],
        "sectors": sectors_payload,
        "cross_asset": cross_asset_payload,
        "calendar": calendar_payload,
        "theory": theory_payload,
        "fred_history": fred_history_payload,
        "latest_daily": latest_daily,
        "latest_monthly": latest_monthly,
        "latest_weekly": latest_weekly,
        "rotation_forecast": rotation_forecast,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    js = "window.MACRO_DATA = " + json.dumps(payload, indent=2, ensure_ascii=False) + ";\n"
    OUT.write_text(js)
    print(f"Wrote {OUT}")
    print(f"  {len(raw_files)} raw days, {len(daily_reports)} daily reports, "
          f"{len(monthly_reports)} monthly reports")
    print(f"  {len(payload['history'])} FRED series in history")


if __name__ == "__main__":
    build()
