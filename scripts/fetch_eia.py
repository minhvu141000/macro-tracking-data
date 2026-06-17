#!/usr/bin/env python3
"""US petroleum inventories from the EIA API — weekly crude/gasoline/distillate
ending stocks (LEVELS, thousand barrels). FRED doesn't carry the current weekly
EIA series, so this is the proper source for "tồn kho dầu thô/xăng".

Needs EIA_API_KEY in .env — free, instant: https://www.eia.gov/opendata/register.php

Uses EIA API v2 (petroleum weekly stocks route). Output: data/eia_history.json,
same shape as a fred_history entry so build_dashboard.build_history() merges it
next to the FRED series and the dashboard charts it in "today's releases".

    python scripts/fetch_eia.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
EIA_API_KEY = os.getenv("EIA_API_KEY", "").strip()
OUT = ROOT / "data" / "eia_history.json"

V2_STOCKS = "https://api.eia.gov/v2/petroleum/stoc/wstk/data/"

# pseudo_id → EIA weekly-stocks series code (level, thousand barrels).
SERIES = {
    "EIA_CRUDE":      {"code": "WCESTUS1", "label": "Crude Oil Stocks (ex-SPR, EIA)"},
    "EIA_GASOLINE":   {"code": "WGTSTUS1", "label": "Total Gasoline Stocks (EIA)"},
    "EIA_DISTILLATE": {"code": "WDISTUS1", "label": "Distillate Fuel Stocks (EIA)"},
}


def _fetch(code: str, n: int = 300) -> list[dict]:
    """Weekly observations for one EIA series → [{date, value}] ascending."""
    params = {
        "api_key": EIA_API_KEY,
        "frequency": "weekly",
        "data[0]": "value",
        "facets[series][]": code,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "offset": "0",
        "length": str(n),
    }
    r = requests.get(V2_STOCKS, params=params, timeout=30)
    if r.status_code != 200:
        print(f"  EIA {code}: HTTP {r.status_code} {r.text[:120]}", file=sys.stderr)
        return []
    rows = (r.json().get("response", {}) or {}).get("data", [])
    out = []
    for row in rows:
        v = row.get("value")
        p = row.get("period")
        if p and v is not None:
            try:
                out.append({"date": p, "value": float(v)})
            except (ValueError, TypeError):
                continue
    out.sort(key=lambda x: x["date"])
    return out


def build() -> dict:
    if not EIA_API_KEY:
        print("  EIA_API_KEY chưa set — bỏ qua (đăng ký free: "
              "https://www.eia.gov/opendata/register.php)", file=sys.stderr)
        return {}
    out = {}
    for pid, spec in SERIES.items():
        hist = _fetch(spec["code"])
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
            "source": "eia",
        }
    return out


def main() -> int:
    out = build()
    if not out:
        print("EIA: không có dữ liệu để ghi (thiếu key hoặc API lỗi).")
        return 0
    OUT.write_text(json.dumps({"schema_version": "1.0",
                               "fetched_at": datetime.now(timezone.utc).isoformat(),
                               "series": out}, indent=2, ensure_ascii=False))
    print(f"Wrote {OUT}")
    for pid, info in out.items():
        print(f"  {pid}: {len(info['history'])} tuần, mới nhất {info['latest']['date']}="
              f"{info['latest']['value']:.0f}K bbl ({info['change_pct']:+}% WoW)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
