#!/usr/bin/env python3
"""Build pre-filled monthly data tables for monthly report.

Reads all data/raw/YYYY-MM-*.json, aggregates non-noise releases grouped by
category, and outputs data/monthly_releases_YYYY-MM.md — data tables already
filled so the LLM agent only needs to add verdicts + conclusions + sector stances.

Usage:
  python scripts/build_monthly_releases.py 2026-06
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Map raw group → display section (mortgage excluded — weekly noise)
GROUP_MAP = {
    "cpi":                "inflation",
    "ppi":                "inflation",
    "jobs_report":        "labor",
    "jobless_claims":     "labor",
    "adp":                "labor",
    "jolts":              "labor",
    "challenger":         "labor",
    "retail_sales":       "growth",
    "ism_manufacturing":  "growth",
    "ism_services":       "growth",
    "durable_goods":      "growth",
    "inventories":        "growth",
    "trade":              "growth",
    "vehicle_sales":      "growth",
    "spglobal_pmi":       "growth",
    "regional_fed":       "growth",
    "construction":       "growth",
    "michigan_sentiment": "confidence",
    "confidence":         "confidence",
    "housing_starts":     "housing",
    "home_sales":         "housing",
    "fed":                "fed_releases",
    # mortgage = weekly repeated, excluded from monthly table
}

SECTION_ORDER = ["inflation", "labor", "growth", "confidence", "housing", "fed_releases"]
SECTION_LABELS = {
    "inflation":     "1. Lạm phát",
    "labor":         "2. Lao động",
    "growth":        "3. Tăng trưởng",
    "confidence":    "4. Niềm tin & Tiêu dùng",
    "housing":       "5. Nhà ở",
    "fed_releases":  "6. Fed & Lãi suất (releases trong tháng)",
}

# Groups where higher actual = worse outcome → above-forecast = 🔴
HIGH_IS_BAD_GROUPS = {"inflation", "fed_releases"}
CLAIMS_KEYWORDS = ("claims", "jobless")


def surprise_emoji(label: str | None, section: str, name: str) -> str:
    if not label:
        return ""
    name_lower = name.lower()
    is_claims = any(k in name_lower for k in CLAIMS_KEYWORDS)

    if section in HIGH_IS_BAD_GROUPS or is_claims:
        return {
            "shock-above":    "🔴 Nóng",
            "above-forecast": "🔴 Nóng",
            "in-line":        "🟡 Inline",
            "shock-below":    "🟢 Cool",
            "below-forecast": "🟢 Cool",
        }.get(label, "")
    else:
        return {
            "shock-above":    "🟢 Tốt",
            "above-forecast": "🟢 Tốt",
            "in-line":        "🟡 Inline",
            "shock-below":    "🔴 Yếu",
            "below-forecast": "🔴 Yếu",
        }.get(label, "")


def clean_name(name: str) -> str:
    """Strip trailing date suffix like (May), (Apr), (Q1 2026); dedupe repeated tags."""
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    # Remove duplicate tags like "(YoY) (YoY)" → "(YoY)"
    name = re.sub(r"\(([^)]+)\)(\s*\(\1\))+", r"(\1)", name)
    return name


def fmt_val(v: object, name: str) -> str:
    """Format a numeric value for the table."""
    if v is None:
        return "—"
    name_lower = name.lower()
    pct_hints = ("yoy", "mom", "rate", "pmi", "sentiment", "confidence",
                 "sales mom", "change", "growth")
    # Values reported in thousands (k): claims, payrolls, JOLTS, starts, permits
    thousands_hints = ("claims", "payrolls", "openings", "starts", "permits",
                       "adp nonfarm", "challenger")
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return str(v)

    # JOLTS Job Openings reported in millions by investing.com (e.g. 7.62 = 7.62M)
    if "openings" in name_lower and abs(fv) < 100:
        return f"{fv:.2f}M"
    # Payrolls / claims / ADP / challenger: raw value in thousands
    if any(h in name_lower for h in thousands_hints):
        # Claims are levels (no + sign); payrolls/ADP are changes (+ sign)
        is_change = any(h in name_lower for h in ("payrolls", "adp", "challenger"))
        prefix = "+" if (is_change and fv > 0) else ""
        if abs(fv) > 999:
            return f"{prefix}{fv:,.0f}k"
        return f"{prefix}{fv:.0f}k"
    if any(h in name_lower for h in pct_hints) and abs(fv) < 200:
        prefix = "+" if fv > 0 else ""
        return f"{prefix}{fv:.1f}%"
    if abs(fv) > 10_000:
        return f"{fv/1000:.0f}k"
    if abs(fv) > 1_000:
        return f"{fv:,.0f}"
    return f"{fv:.2f}".rstrip("0").rstrip(".")


def vs_prev(actual: object, previous: object, name: str) -> str:
    if actual is None or previous is None:
        return "—"
    try:
        diff = float(actual) - float(previous)
    except (TypeError, ValueError):
        return "—"
    if abs(diff) < 0.005:
        return "→"
    arrow = "↑" if diff > 0 else "↓"
    name_lower = name.lower()
    if any(h in name_lower for h in ("yoy", "rate", "pmi", "sentiment", "confidence")):
        return f"{arrow} {diff:+.2f}pp"
    return arrow


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: build_monthly_releases.py YYYY-MM", file=sys.stderr)
        return 1

    month = sys.argv[1]
    raw_dir = ROOT / "data" / "raw"
    files = sorted(raw_dir.glob(f"{month}-*.json"))
    if not files:
        print(f"No raw files found for {month}", file=sys.stderr)
        return 1

    sections: dict[str, list[dict]] = {s: [] for s in SECTION_ORDER}
    seen: set[str] = set()  # dedupe by date+name

    for f in files:
        data = json.loads(f.read_text())
        date_str = data.get("date", f.stem)
        try:
            dt = datetime.fromisoformat(date_str)
            date_display = dt.strftime("%d/%m")
        except Exception:
            date_display = date_str

        for r in data.get("releases", []):
            if r.get("is_noise"):
                continue
            country = r.get("country", "US")
            if country and country not in ("US", "", "United States"):
                continue

            group = r.get("group", "other")
            section = GROUP_MAP.get(group)
            if not section:
                continue

            parsed = r.get("parsed") or {}
            actual = parsed.get("actual")
            forecast = parsed.get("forecast")
            previous = parsed.get("previous")

            if actual is None:
                continue
            # Skip sub-components without market forecast (index levels, n.s.a.)
            if forecast is None and section not in ("fed_releases",):
                continue

            name = clean_name(r.get("name", ""))
            key = f"{date_display}|{name}"
            if key in seen:
                continue
            seen.add(key)

            surprise = r.get("surprise") or {}
            s_label = surprise.get("label")

            sections[section].append({
                "date":        date_display,
                "name":        name,
                "actual":      fmt_val(actual, name),
                "forecast":    fmt_val(forecast, name) if forecast is not None else "—",
                "vs_previous": vs_prev(actual, previous, name),
                "surprise":    surprise_emoji(s_label, section, name),
            })

    # Build markdown
    lines: list[str] = [
        f"# Monthly releases — {month}",
        "",
        "_Auto-generated by build_monthly_releases.py._",
        "_Dữ liệu đã điền sẵn. Agent chỉ cần thêm: verdict header, 2-câu kết luận, bảng sector, cross-asset._",
        "",
    ]

    for section in SECTION_ORDER:
        label = SECTION_LABELS[section]
        releases = sections[section]

        lines.append(f"## {label} — [VERDICT]")
        lines.append("")
        if not releases:
            lines.append("_Không có release trong tháng này._")
        else:
            lines.append("| Ngày | Chỉ số | Actual | Forecast | vs Previous | Surprise |")
            lines.append("|---|---|---|---|---|---|")
            for r in releases:
                lines.append(
                    f"| {r['date']} | {r['name']} | {r['actual']} "
                    f"| {r['forecast']} | {r['vs_previous']} | {r['surprise']} |"
                )
        lines.append("")
        lines.append("**Kết luận:** [2 câu tối đa]")
        lines.append("")
        lines.append("---")
        lines.append("")

    out_path = ROOT / "data" / f"monthly_releases_{month}.md"
    out_path.write_text("\n".join(lines))

    total = sum(len(sections[s]) for s in SECTION_ORDER)
    print(f"Wrote {out_path}")
    print(f"  {total} releases across {len(files)} raw files")
    for s in SECTION_ORDER:
        print(f"  {SECTION_LABELS[s]}: {len(sections[s])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
