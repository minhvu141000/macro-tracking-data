#!/usr/bin/env python3
"""Score last month's sector calls against realized relative performance.

Closes the feedback loop that turns "tracking" into "decision-making": every
month, grade the prior monthly report's 11 GICS stances against what each sector
ACTUALLY did vs SPY, and report a hit rate. Over time this surfaces whether the
system's calls add value — and which call types (OW/UW/Neutral) work best.

Method (deterministic):
  1. Parse sector → stance from the latest data/monthly/<YYYY-MM>.md GICS table.
  2. Read realized relative strength (rs_1m) from data/sectors_lite.json.
  3. Grade: bullish call wants rs_1m > +1; bearish wants rs_1m < -1; neutral wants |rs_1m| ≤ 2.
  4. Append a dated section to data/monthly/scorecard.md.

Note: rs_1m is trailing-from-today (~last 21 sessions), an APPROXIMATION of the
"since the call" window. Good enough for a directional scorecard; not P&L.

    python scripts/build_scorecard.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MONTHLY_DIR = ROOT / "data" / "monthly"
SECTORS_LITE = ROOT / "data" / "sectors_lite.json"
OUT = MONTHLY_DIR / "scorecard.md"

TICKERS = {"XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC"}


def classify_stance(cell: str) -> str | None:
    """Map a free-text stance cell → bullish | bearish | neutral. Order matters."""
    s = cell.lower()
    if any(w in s for w in ("underweight", "avoid", "/uw", " uw", "bearish")):
        return "bearish"
    if any(w in s for w in ("overweight", "light ow", " ow", "bullish")):
        return "bullish"
    if any(w in s for w in ("neutral", "watch", "stalking", "hold")):
        return "neutral"
    return None


def parse_monthly_stances(path: Path) -> dict[str, str]:
    """Extract {ticker: stance_class} from the GICS table rows of a monthly report."""
    stances: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        m = re.search(r"\b(XL[A-Z]{1,2})\b", cells[0])
        if not m or m.group(1) not in TICKERS:
            continue
        cls = classify_stance(cells[1])
        if cls:
            stances[m.group(1)] = cls
    return stances


def grade(stance: str, rs_1m: float | None) -> str:
    if rs_1m is None:
        return "n/a"
    if stance == "bullish":
        return "HIT" if rs_1m > 1 else ("MISS" if rs_1m < -1 else "~")
    if stance == "bearish":
        return "HIT" if rs_1m < -1 else ("MISS" if rs_1m > 1 else "~")
    # neutral
    return "HIT" if abs(rs_1m) <= 2 else "MISS"


def latest_monthly() -> Path | None:
    files = sorted(MONTHLY_DIR.glob("[0-9]*.md"))
    return files[-1] if files else None


def build() -> str:
    mfile = latest_monthly()
    if not mfile:
        return ""
    stances = parse_monthly_stances(mfile)
    if not stances:
        print(f"  WARNING: no parseable GICS stances in {mfile.name}", file=sys.stderr)
        return ""
    sectors = json.loads(SECTORS_LITE.read_text()).get("sectors", {})

    rows, hits, graded = [], 0, 0
    for tk, stance in sorted(stances.items()):
        info = sectors.get(tk, {})
        rs = info.get("rs_1m")
        name = info.get("name", tk)
        g = grade(stance, rs)
        if g in ("HIT", "MISS"):
            graded += 1
            if g == "HIT":
                hits += 1
        rs_txt = f"{rs:+.1f}%" if rs is not None else "—"
        icon = {"HIT": "✅", "MISS": "❌", "~": "➖", "n/a": "❔"}[g]
        rows.append(f"| {tk} {name} | {stance} | {rs_txt} | {icon} {g} |")

    hit_rate = f"{hits}/{graded} ({round(hits/graded*100)}%)" if graded else "n/a"
    today = date.today().isoformat()
    lines = [
        f"## Scorecard {today} — đánh giá calls từ `{mfile.stem}`",
        "",
        f"**Hit rate:** {hit_rate}  ·  nguồn realized: `sectors_lite.json` rs_1m (RS vs SPY ~1 tháng).",
        "",
        "| Sector | Call | RS 1M thực tế | Kết quả |",
        "|---|---|---|---|",
        *rows,
        "",
        "> Quy tắc chấm: bullish cần RS>+1%; bearish cần RS<−1%; neutral cần |RS|≤2%. "
        "`➖` = đúng hướng nhưng chưa đủ ngưỡng. RS 1M là xấp xỉ (trailing từ hôm nay), không phải P&L.",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    section = build()
    if not section:
        print("Scorecard: nothing to score (no monthly report or unparseable).")
        return 0
    # Prepend newest scorecard above older ones (keep history).
    existing = OUT.read_text() if OUT.exists() else "# Sector Calls Scorecard\n\n"
    if not existing.startswith("# Sector Calls Scorecard"):
        existing = "# Sector Calls Scorecard\n\n" + existing
    header, _, rest = existing.partition("\n\n")
    OUT.write_text(f"{header}\n\n{section}{rest}")
    print(f"Wrote {OUT}")
    print(section.split("\n")[2])  # the hit-rate line
    return 0


if __name__ == "__main__":
    sys.exit(main())
