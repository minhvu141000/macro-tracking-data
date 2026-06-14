#!/usr/bin/env python3
"""Deterministic enrichment for investing.com releases.

Moves the "hard logic" out of the LLM and into code so ANY agent — even an
external one that only reads the raw JSON — gets a consistent analysis
scaffold for free:

  - `parsed`:        numeric actual/forecast/previous (handles %, K, M, B, commas)
  - `surprise`:      score + label vs forecast (None when no forecast)
  - `vs_previous`:   change vs previous print (direction + delta)
  - `group`:         which release cluster this row belongs to (NFP, CPI, Michigan…)
  - `is_noise`:      True for low-signal rows (CFTC, auctions, EIA) → analyst keeps brief

Run standalone to backfill existing files:
    python scripts/enrich_releases.py            # enrich all data/raw/*.json
    python scripts/enrich_releases.py 2026-06-12 # one date
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

# ---- numeric parsing --------------------------------------------------------

_SUFFIX = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def parse_value(raw: str | None) -> float | None:
    """'4.6%' -> 4.6 | '265K' -> 265 | '-1.3K' -> -1.3 | '1,250' -> 1250 | '4.25-4.50%' -> 4.375.

    Note: % and K/M/B are stripped to their face number — we compare like-for-like
    (actual vs forecast carry the same unit), so the magnitude is what matters, not
    the absolute scale. A 'K' on both sides cancels in the surprise ratio.
    """
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "")
    if not s or s in ("-", "—", "\xa0"):
        return None
    # range like "4.25-4.50%" → midpoint
    m = re.match(r"^(-?\d+\.?\d*)\s*-\s*(-?\d+\.?\d*)\s*%?$", s)
    if m:
        return (float(m.group(1)) + float(m.group(2))) / 2
    mult = 1.0
    s2 = s.rstrip("%")
    if s2 and s2[-1].upper() in _SUFFIX:
        mult = _SUFFIX[s2[-1].upper()]
        s2 = s2[:-1]
        # keep K/M/B as face value (265K → 265) so deviation ratio stays unit-free
        mult = 1.0
    try:
        return float(s2) * mult
    except ValueError:
        return None


# ---- surprise scoring -------------------------------------------------------

def score_surprise(actual: float | None, forecast: float | None) -> dict[str, Any] | None:
    """Deviation of actual from forecast, normalized to a rough z-score.

    z = (actual - forecast) / |forecast * 0.05|   (5% of forecast ≈ 1 'sigma')
    Falls back to absolute deviation when forecast is ~0 (e.g. MoM 0.0%).

    Returns NEUTRAL language (above/below/in-line) — NOT beat/miss — because the
    good/bad sign flips by indicator type (hot CPI = bad, hot NFP = good). The
    analyst decides direction from indicator semantics.
    """
    if actual is None or forecast is None:
        return None
    dev = actual - forecast
    denom = abs(forecast) * 0.05
    if denom < 1e-9:  # forecast ~0 → use absolute deviation scaled to 0.1 unit ≈ 1σ
        z = dev / 0.1
    else:
        z = dev / denom
    az = abs(z)
    if az < 0.5:
        label = "in-line"
    elif az < 1.5:
        label = "above-forecast" if z > 0 else "below-forecast"
    else:
        label = "shock-above" if z > 0 else "shock-below"
    return {
        "deviation": round(dev, 4),
        "z_score": round(z, 2),
        "label": label,
    }


def vs_previous(actual: float | None, previous: float | None) -> dict[str, Any] | None:
    if actual is None or previous is None:
        return None
    delta = actual - previous
    return {
        "delta": round(delta, 4),
        "direction": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
    }


# ---- grouping ---------------------------------------------------------------
# Order matters: first match wins. Specific patterns before generic ones.
GROUP_RULES: list[tuple[str, str]] = [
    # Labor — jobs report cluster
    (r"nonfarm payroll|private nonfarm|government payroll|manufacturing payroll|"
     r"average hourly|average weekly hours|participation rate|u6 unemployment|"
     r"\bunemployment rate\b", "jobs_report"),
    (r"jobless claims|continuing claims|claims 4-week", "jobless_claims"),
    (r"adp ", "adp"),
    (r"challenger", "challenger"),
    (r"jolts|job openings", "jolts"),
    # Inflation
    (r"\bcpi\b|consumer price|cleveland cpi", "cpi"),
    (r"\bppi\b|producer price", "ppi"),
    (r"pce price|core pce|pce prices", "pce_inflation"),
    (r"michigan|uom |inflation expectations", "michigan_sentiment"),
    # Growth
    (r"\bgdp\b|gdp price|gdp sales|corporate profits", "gdp"),
    (r"ism manufacturing|ism mfg", "ism_manufacturing"),
    (r"ism non-manufacturing|ism services|ism svc", "ism_services"),
    (r"s&p global.*pmi|composite pmi|services pmi|manufacturing pmi", "spglobal_pmi"),
    (r"retail sales|retail control", "retail_sales"),
    (r"durable goods|factory orders|goods orders|durables excluding", "durable_goods"),
    (r"industrial production|capacity utilization|manufacturing production", "industrial_production"),
    (r"personal income|personal spending|real personal|real consumer", "income_spending"),
    (r"vehicle sales|car sales|truck sales", "vehicle_sales"),
    (r"construction spending", "construction"),
    (r"wholesale inventories|retail inventories|business inventories", "inventories"),
    (r"chicago pmi|chicago fed|richmond|dallas fed|philadelphia fed|empire|kansas city", "regional_fed"),
    # Confidence
    (r"consumer confidence|consumer sentiment|nfib|ibd/tipp|economic optimism|"
     r"business confidence|employment trends", "confidence"),
    # Housing
    (r"housing starts|building permits", "housing_starts"),
    (r"existing home|new home sales|pending home", "home_sales"),
    (r"house price|case-shiller|cs hpi|fhfa", "home_prices"),
    (r"mba |mortgage|purchase index|refinance index", "mortgage"),
    # Trade / fiscal / money
    (r"trade balance|goods trade|\bexports\b|\bimports\b", "trade"),
    (r"federal budget|treasury budget|budget balance", "fiscal"),
    (r"m2 money|money supply|consumer credit", "money_credit"),
    # Fed
    (r"fomc|fed .*speaks|fed governor|fed chair|fed vice|beige book|"
     r"interest rate decision|rate decision", "fed"),
    # Noise / low-signal (kept brief by analyst)
    (r"cftc", "cftc_positions"),
    (r"baker hughes|rig count", "rig_count"),
    (r"eia|crude oil|gasoline|distillate|heating oil|natural gas storage|"
     r"refinery|cushing|opec|api weekly|wasde", "energy_inventory"),
    (r"bill auction|note auction|bond auction", "auctions"),
    (r"redbook|fed's balance sheet|reserve balances", "fed_plumbing"),
]

NOISE_GROUPS = {
    "cftc_positions", "rig_count", "energy_inventory", "auctions", "fed_plumbing",
}


def classify_group(name: str) -> str:
    low = name.lower()
    for pattern, group in GROUP_RULES:
        if re.search(pattern, low):
            return group
    return "other"


# ---- main enrichment --------------------------------------------------------

def enrich_release(rel: dict[str, Any]) -> dict[str, Any]:
    a = parse_value(rel.get("actual"))
    f = parse_value(rel.get("forecast"))
    p = parse_value(rel.get("previous"))
    group = classify_group(rel.get("name") or "")
    rel["parsed"] = {"actual": a, "forecast": f, "previous": p}
    rel["surprise"] = score_surprise(a, f)
    rel["vs_previous"] = vs_previous(a, p)
    rel["group"] = group
    rel["is_noise"] = group in NOISE_GROUPS
    return rel


def enrich_releases(releases: list[dict[str, Any]]) -> dict[str, Any]:
    """Enrich each release in place; return a summary block for the payload."""
    for rel in releases:
        enrich_release(rel)

    signal = [r for r in releases if not r.get("is_noise")]
    scored = [r for r in signal if r.get("surprise")]
    # surprise_count counts SIGNAL events with |z| >= 0.5, deduped by group
    surprised_groups = {
        r["group"] for r in scored if abs(r["surprise"]["z_score"]) >= 0.5
    }
    groups_present = sorted({r["group"] for r in signal})
    return {
        "signal_release_count": len(signal),
        "noise_release_count": len(releases) - len(signal),
        "surprise_count": len(surprised_groups),
        "groups_present": groups_present,
        "surprised_groups": sorted(surprised_groups),
    }


def build_inflation_context(fred_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Pull the latest hard-data inflation readings into one block.

    Forces every agent to SEE hard-data even on a soft-data day — so it can't
    declare 'disinflation confirmed / dovish' off a single sentiment survey
    while Core PCE is still >3%.

    `hard_data_hot` = True when any core gauge is still above the Fed's comfort
    zone (Core CPI or Core PCE YoY > 3.0%, or headline CPI YoY > 3.5%).
    """
    def get(sid: str, key: str) -> float | None:
        s = fred_snapshot.get(sid) or {}
        if key == "yoy":
            return s.get("yoy_pct")
        if key == "3mo":
            return s.get("mo3_annualized_pct")
        return None

    ctx = {
        "cpi_yoy": get("CPIAUCSL", "yoy"),
        "cpi_3mo_ann": get("CPIAUCSL", "3mo"),
        "core_cpi_yoy": get("CPILFESL", "yoy"),
        "core_cpi_3mo_ann": get("CPILFESL", "3mo"),
        "pce_yoy": get("PCEPI", "yoy"),
        "core_pce_yoy": get("PCEPILFE", "yoy"),
        "core_pce_3mo_ann": get("PCEPILFE", "3mo"),
    }
    core_cpi = ctx["core_cpi_yoy"]
    core_pce = ctx["core_pce_yoy"]
    cpi = ctx["cpi_yoy"]
    hot = bool(
        (core_cpi is not None and core_cpi > 3.0)
        or (core_pce is not None and core_pce > 3.0)
        or (cpi is not None and cpi > 3.5)
    )
    ctx["hard_data_hot"] = hot
    if hot:
        bits = []
        if core_pce is not None:
            bits.append(f"Core PCE YoY {core_pce}%")
        if cpi is not None:
            bits.append(f"CPI YoY {cpi}%")
        ctx["note"] = (
            "Hard-data lạm phát VẪN NÓNG (" + ", ".join(bits) + "). "
            "Soft-data/khảo sát dovish CHƯA đủ xác nhận disinflation — "
            "báo cáo phải đối chiếu, không tuyên bố 'risk-on bền/dovish hẳn' một chiều."
        )
    else:
        ctx["note"] = "Hard-data lạm phát đã về vùng dễ chịu (core < 3%)."
    return ctx


def enrich_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    releases = data.get("releases", [])
    summary = enrich_releases(releases)
    data["releases"] = releases
    data["release_summary"] = summary
    if data.get("fred_snapshot"):
        data["inflation_context"] = build_inflation_context(data["fred_snapshot"])
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    args = sys.argv[1:]
    if args:
        targets = [RAW_DIR / f"{d}.json" for d in args]
    else:
        targets = sorted(RAW_DIR.glob("*.json"))
    for p in targets:
        if not p.exists():
            print(f"  skip (missing): {p.name}")
            continue
        s = enrich_file(p)
        print(f"  {p.name}: {s['signal_release_count']} signal / "
              f"{s['noise_release_count']} noise, "
              f"surprise_count={s['surprise_count']}, "
              f"groups={s['groups_present']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
