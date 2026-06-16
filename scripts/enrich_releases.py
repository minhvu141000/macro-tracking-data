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


# CPI sub-component FRED series → label, ranked to show what pulls inflation up/down.
CPI_DRIVER_SERIES = {
    "CUSR0000SAH1": "Shelter (Nhà ở)",
    "CPIUFDSL": "Food (Thực phẩm)",
    "CPIENGSL": "Energy (Năng lượng)",
    "CUSR0000SACL1E": "Core Goods (Hàng hoá lõi)",
    "CUSR0000SASLE": "Core Services (Dịch vụ lõi)",
}

# GDP contribution FRED series (pp at annual rate) → label. These sum to GDP rate.
GDP_CONTRIB_SERIES = {
    "DPCERY2Q224SBEA": "Tiêu dùng (PCE)",
    "A006RY2Q224SBEA": "Đầu tư tư nhân",
    "A019RY2Q224SBEA": "Xuất khẩu ròng (Net Exports)",
    "A822RY2Q224SBEA": "Chi tiêu chính phủ",
}


def build_inflation_drivers(fred_snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Rank CPI sub-components by momentum so the report can name which group is
    pulling inflation UP vs DOWN — deterministically, not LLM guesswork.

    Momentum = 3-mo annualized % (smoother) with MoM% fallback. Highest = top
    up-driver; lowest (often negative) = top disinflationary driver.
    """
    drivers = []
    for sid, label in CPI_DRIVER_SERIES.items():
        s = fred_snapshot.get(sid) or {}
        mom, yoy, mo3 = s.get("mom_pct"), s.get("yoy_pct"), s.get("mo3_annualized_pct")
        if mom is None and yoy is None:
            continue
        drivers.append({
            "component": label, "series_id": sid,
            "mom_pct": mom, "yoy_pct": yoy, "mo3_annualized_pct": mo3,
        })
    if not drivers:
        return None

    def momentum(d):
        return d["mo3_annualized_pct"] if d["mo3_annualized_pct"] is not None else (d["mom_pct"] or 0.0)

    ranked = sorted(drivers, key=momentum, reverse=True)
    return {
        "ranked_by_momentum": ranked,
        "top_up": ranked[0]["component"],
        "top_down": ranked[-1]["component"],
        "note": (
            f"Kéo lạm phát LÊN mạnh nhất: {ranked[0]['component']} "
            f"(3mo ann {momentum(ranked[0])}%). "
            f"Kéo XUỐNG/giảm áp lực nhất: {ranked[-1]['component']} "
            f"(3mo ann {momentum(ranked[-1])}%)."
        ),
    }


def build_growth_context(fred_snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Read the 4 GDP contribution series (pp) — they sum to the headline GDP rate —
    and rank to surface the locomotive (đầu tàu) vs the biggest drag (lực cản).
    """
    def value(sid: str) -> float | None:
        s = fred_snapshot.get(sid) or {}
        latest = s.get("latest") or {}
        v = latest.get("value") if isinstance(latest, dict) else None
        return round(v, 2) if isinstance(v, (int, float)) else None

    contribs = []
    for sid, label in GDP_CONTRIB_SERIES.items():
        v = value(sid)
        if v is None:
            continue
        contribs.append({"component": label, "series_id": sid, "contribution_pp": v})
    if not contribs:
        return None

    ranked = sorted(contribs, key=lambda d: d["contribution_pp"], reverse=True)
    gdp_rate = value("A191RL1Q225SBEA")
    return {
        "gdp_growth_pct": gdp_rate,
        "ranked_by_contribution": ranked,
        "locomotive": ranked[0]["component"],
        "biggest_drag": ranked[-1]["component"],
        "note": (
            f"Đầu tàu kéo GDP: {ranked[0]['component']} (+{ranked[0]['contribution_pp']}pp). "
            f"Lực cản lớn nhất: {ranked[-1]['component']} ({ranked[-1]['contribution_pp']:+}pp). "
            f"Tổng tăng trưởng GDP QoQ ann. = {gdp_rate}%."
        ),
    }


# Polarity for the Economic Surprise Index: does "above forecast" mean a STRONGER
# economy (+1) or weaker (-1)? Inflation groups are tracked on a SEPARATE axis.
GROWTH_POLARITY: dict[str, int] = {
    "jobs_report": +1, "gdp": +1, "ism_manufacturing": +1, "ism_services": +1,
    "spglobal_pmi": +1, "retail_sales": +1, "durable_goods": +1,
    "industrial_production": +1, "income_spending": +1, "confidence": +1,
    "home_sales": +1, "housing_starts": +1, "jolts": +1, "adp": +1,
    "vehicle_sales": +1, "construction": +1, "regional_fed": +1,
    "jobless_claims": -1, "challenger": -1,  # higher = weaker labor
}
INFLATION_GROUPS = {"cpi", "ppi", "pce_inflation", "michigan_sentiment"}


def day_surprise_score(releases: list[dict[str, Any]]) -> dict[str, Any]:
    """Net signed surprise for one day → feeds the Economic Surprise Index.

    growth_score = Σ (polarity × z_score) over growth/labor releases (deduped by
    group, capped at ±3σ per release to stop one shock dominating). Positive =
    data beating expectations on the strong-economy side → risk-on tailwind.
    inflation_score = Σ z_score over inflation releases (positive = hotter than
    expected → hawkish). Kept on a separate axis so growth & price surprises
    don't cancel.
    """
    seen_growth: dict[str, float] = {}
    seen_infl: dict[str, float] = {}
    for r in releases:
        if r.get("is_noise") or not r.get("surprise"):
            continue
        g = r.get("group", "other")
        z = max(-3.0, min(3.0, r["surprise"]["z_score"]))
        if g in GROWTH_POLARITY:
            # keep the largest-magnitude print per group for the day
            signed = GROWTH_POLARITY[g] * z
            if abs(signed) > abs(seen_growth.get(g, 0.0)):
                seen_growth[g] = signed
        elif g in INFLATION_GROUPS:
            if abs(z) > abs(seen_infl.get(g, 0.0)):
                seen_infl[g] = z
    return {
        "growth_score": round(sum(seen_growth.values()), 2),
        "inflation_score": round(sum(seen_infl.values()), 2),
        "n_growth": len(seen_growth),
        "n_inflation": len(seen_infl),
    }


def build_cycle_context(fred_snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Deterministic 'where in the cycle' gauge — the #1 driver of sector rotation.

    Two battle-tested recession signals computed from data we already pull:
      - Sahm Rule (from UNRATE): 3-mo avg unemployment minus its trailing-12mo low.
        ≥ 0.50 pp = recession has likely already started. Real-time, rarely false.
      - Yield curve (T10Y2Y, + 10Y-3M from DGS10/DGS3MO): inversion = classic
        12-18mo recession lead; the *un-inversion* (re-steepening after inversion)
        is the more imminent warning — recessions usually start AFTER it re-steepens.

    Needs full-ish history (UNRATE monthly ≥15 obs; T10Y2Y daily). Pass the FULL
    snapshot (fred_history.json), not the 3-obs trimmed daily snapshot.
    Returns None if neither signal is computable.
    """
    out: dict[str, Any] = {}

    # --- Sahm Rule from UNRATE (monthly) ---
    unrate = (fred_snapshot.get("UNRATE") or {}).get("history") or []
    if len(unrate) >= 15:
        vals = [h["value"] for h in unrate]
        ma3 = [round(sum(vals[i - 2 : i + 1]) / 3, 2) for i in range(2, len(vals))]
        current_ma3 = ma3[-1]
        # Trailing 12-month low of the 3-mo avg (months prior to current)
        window = ma3[-13:-1] if len(ma3) >= 13 else ma3[:-1]
        trailing_min = min(window) if window else current_ma3
        sahm = round(current_ma3 - trailing_min, 2)
        out["sahm"] = {
            "value": sahm,
            "triggered": sahm >= 0.50,
            "current_3mo_avg_unemp": current_ma3,
            "trailing_12mo_low": round(trailing_min, 2),
            "note": (
                f"Sahm {sahm:+.2f}pp — "
                + ("ĐÃ KÍCH HOẠT (≥0.50): suy thoái nhiều khả năng đã bắt đầu."
                   if sahm >= 0.50 else
                   f"chưa kích hoạt (ngưỡng 0.50). Thất nghiệp 3mo-avg {current_ma3}% "
                   f"vs đáy 12 tháng {round(trailing_min,2)}%.")
            ),
        }

    # --- Yield curve ---
    t10y2y_hist = (fred_snapshot.get("T10Y2Y") or {}).get("history") or []
    dgs10 = ((fred_snapshot.get("DGS10") or {}).get("latest") or {}).get("value")
    dgs3mo = ((fred_snapshot.get("DGS3MO") or {}).get("latest") or {}).get("value")
    if t10y2y_hist:
        cur = t10y2y_hist[-1]["value"]
        inverted = cur < 0
        # How long since the curve last had the opposite sign → duration of current regime
        days_in_regime = 0
        for h in reversed(t10y2y_hist):
            if (h["value"] < 0) == inverted:
                days_in_regime += 1
            else:
                break
        # Did it dis-invert recently? (was negative anywhere in window, now positive)
        was_inverted = any(h["value"] < 0 for h in t10y2y_hist)
        dis_inverted = (not inverted) and was_inverted
        spread_10y3m = (
            round(dgs10 - dgs3mo, 2) if dgs10 is not None and dgs3mo is not None else None
        )
        if inverted:
            regime = "inverted"
            curve_note = (
                f"2s10s ĐẢO NGƯỢC {cur:+.2f} ({days_in_regime} phiên) — "
                "tín hiệu suy thoái cổ điển (thường dẫn trước 12-18 tháng)."
            )
        elif dis_inverted:
            regime = "dis-inverted"
            curve_note = (
                f"2s10s đã DỐC LẠI {cur:+.2f} sau giai đoạn đảo ngược ({days_in_regime} phiên dương) — "
                "CẢNH BÁO: suy thoái thường khởi phát SAU khi đường cong dốc lại, không phải lúc đảo ngược."
            )
        else:
            regime = "normal"
            curve_note = f"2s10s dương bình thường {cur:+.2f} ({days_in_regime} phiên), chưa từng đảo trong cửa sổ dữ liệu."
        out["yield_curve"] = {
            "spread_2s10s": cur,
            "spread_10y3m": spread_10y3m,
            "regime": regime,
            "days_in_regime": days_in_regime,
            "note": curve_note,
        }

    if not out:
        return None

    # One-line composite for the report's Market Pulse
    bits = []
    if "sahm" in out:
        s = out["sahm"]
        bits.append(f"Sahm {s['value']:+.2f} ({'KÍCH HOẠT' if s['triggered'] else 'an toàn'})")
    if "yield_curve" in out:
        bits.append(f"Đường cong: {out['yield_curve']['regime']} ({out['yield_curve']['spread_2s10s']:+.2f})")
    out["summary"] = " | ".join(bits)
    return out


def _load_full_fred_history() -> dict[str, Any]:
    """The trimmed snapshot in raw files only has 3 obs — too few for Sahm/curve.
    Fall back to the full-history file (overwritten daily) for cycle_context backfill.
    """
    fh = ROOT / "data" / "fred_history.json"
    if fh.exists():
        try:
            return json.loads(fh.read_text()).get("fred_snapshot", {})
        except Exception:
            return {}
    return {}


def enrich_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    releases = data.get("releases", [])
    summary = enrich_releases(releases)
    summary["day_surprise_score"] = day_surprise_score(releases)
    data["releases"] = releases
    data["release_summary"] = summary
    snap = data.get("fred_snapshot")
    if snap:
        ctx = build_inflation_context(snap)
        ctx["drivers"] = build_inflation_drivers(snap)
        data["inflation_context"] = ctx
        data["growth_context"] = build_growth_context(snap)
        # Cycle gauge needs deep history → use full-history file, not the 3-obs trim.
        data["cycle_context"] = build_cycle_context(_load_full_fred_history() or snap)
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
