#!/usr/bin/env python3
"""Deterministic macro → sector ROTATION engine.

The system's #1 job: turn today's tracked macro state into a ranked view of which
GICS sectors are positioned to RECEIVE capital rotation — so a downstream
stock-picking agent can filter names inside the flagged sectors.

Why deterministic (not LLM): the macro→sector cheat-sheet that used to live as
prose in the agents is encoded here as a SENSITIVITY MATRIX (sector × factor).
Same inputs → same ranking, every day, and the calls are scoreable.

Pipeline (read-only on its inputs, all already produced earlier in the daily flow):
  surprise_index.json   → growth/inflation surprise axes (ESI)
  data/raw/<latest>.json → cycle_context (Sahm + yield-curve regime), inflation_context
  cross_asset_lite.json → 10Y yield, DXY, WTI, Copper, VIX  (rates/USD/commodities/risk)
  sectors_lite.json     → per-sector RS, rs_slope (momentum), breadth_thrust, trend

Two axes are kept SEPARATE on purpose:
  • macro_tilt  — does the macro backdrop favor this sector? (forward-ish)
  • price_momentum — is money already moving in? (rs_slope, breadth_thrust)
The interesting quadrant for the user is macro-positive but price-not-yet-extended
→ phase = EARLY: rotation arriving, the prime hunting ground.

Output: data/sector_rotation_latest.json   (machine-readable handoff)

    python scripts/build_sector_rotation.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW_DIR = DATA / "raw"
OUT = DATA / "sector_rotation_latest.json"
HISTORY = DATA / "sector_rotation_history.json"   # daily evidence feed → weekly confirmation
HISTORY_MAX = 90                                   # keep ~3 months of daily snapshots

SECTOR_NAMES = {
    "XLK": "Technology", "XLF": "Financials", "XLE": "Energy", "XLV": "Healthcare",
    "XLY": "Consumer Discretionary", "XLP": "Consumer Staples", "XLI": "Industrials",
    "XLB": "Materials", "XLU": "Utilities", "XLRE": "Real Estate",
    "XLC": "Communication Services",
}

# Factor order. Each factor is normalized to roughly [-1.5, +1.5] (positive = the
# direction named in the comment). Sensitivities below are multiplied by these.
FACTORS = ["G", "I", "R", "DEF", "USD", "OIL", "CU", "RISK"]
FACTOR_LABELS = {
    "G": "Tăng trưởng (surprise)", "I": "Lạm phát (surprise, +=nóng)",
    "R": "Lãi suất 10Y (+=tăng)", "DEF": "Nhu cầu phòng thủ (late-cycle/recession)",
    "USD": "USD (+=mạnh)", "OIL": "Dầu WTI (+=tăng)", "CU": "Đồng (+=tăng)",
    "RISK": "Khẩu vị rủi ro (+=risk-on)",
}

# Sensitivity matrix: how each sector responds to each macro factor.
# Encoded from the macro→sector cheat-sheet in .claude/agents/macro-trend.md.
SENS = {
    "XLK":  {"G": +1.0, "I": -1.0, "R": -1.5, "DEF": -1.0, "USD": -0.5, "OIL":  0.0, "CU":  0.0, "RISK": +1.5},
    "XLF":  {"G": +1.0, "I": +0.5, "R": +1.5, "DEF": -1.5, "USD": +0.3, "OIL":  0.0, "CU":  0.0, "RISK": +0.5},
    "XLE":  {"G": +0.5, "I": +1.5, "R": +0.3, "DEF": -0.3, "USD": -0.5, "OIL": +2.0, "CU": +0.3, "RISK": +0.3},
    "XLV":  {"G": -0.3, "I":  0.0, "R": -0.3, "DEF": +1.5, "USD":  0.0, "OIL":  0.0, "CU":  0.0, "RISK": -0.5},
    "XLY":  {"G": +1.5, "I": -0.5, "R": -1.0, "DEF": -1.5, "USD":  0.0, "OIL": -0.5, "CU":  0.0, "RISK": +1.5},
    "XLP":  {"G": -1.0, "I":  0.0, "R":  0.0, "DEF": +1.5, "USD":  0.0, "OIL": -0.3, "CU":  0.0, "RISK": -1.0},
    "XLI":  {"G": +1.5, "I":  0.0, "R":  0.0, "DEF": -1.5, "USD": -0.5, "OIL":  0.0, "CU": +1.0, "RISK": +1.0},
    "XLB":  {"G": +1.0, "I": +0.5, "R":  0.0, "DEF": -1.0, "USD": -1.0, "OIL": +0.3, "CU": +1.5, "RISK": +1.0},
    "XLU":  {"G": -1.0, "I":  0.0, "R": -1.5, "DEF": +1.5, "USD":  0.0, "OIL":  0.0, "CU":  0.0, "RISK": -1.0},
    "XLRE": {"G":  0.0, "I": -0.3, "R": -2.0, "DEF": -0.3, "USD":  0.0, "OIL":  0.0, "CU":  0.0, "RISK": +0.5},
    "XLC":  {"G": +1.0, "I": -0.5, "R": -0.5, "DEF": -0.5, "USD":  0.0, "OIL":  0.0, "CU":  0.0, "RISK": +1.0},
}


def _clip(x: float, lo: float = -1.5, hi: float = 1.5) -> float:
    return max(lo, min(hi, x))


def _zscores(vals: dict[str, float]) -> dict[str, float]:
    """Cross-sectional z-score across the 11 sectors. std==0 → all zeros."""
    xs = list(vals.values())
    n = len(xs)
    if n == 0:
        return {}
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / n
    std = var ** 0.5
    if std == 0:
        return {k: 0.0 for k in vals}
    return {k: round((v - mean) / std, 2) for k, v in vals.items()}


def _latest_raw() -> dict:
    files = sorted(RAW_DIR.glob("[0-9]*.json"))
    return json.loads(files[-1].read_text()) if files else {}


def _load(name: str) -> dict:
    p = DATA / name
    return json.loads(p.read_text()) if p.exists() else {}


def build_factors() -> tuple[dict[str, float], dict[str, dict], str]:
    """Return (factor_values, factor_meta, regime_summary)."""
    si = _load("surprise_index.json").get("latest", {})
    raw = _latest_raw()
    cyc = raw.get("cycle_context") or {}
    cross = _load("cross_asset_lite.json").get("assets", {})

    def cross_ret(tk: str) -> float | None:
        a = cross.get(tk) or {}
        return a.get("ret_1m")

    f: dict[str, float] = {}
    meta: dict[str, dict] = {}

    # --- Growth & inflation surprise (ESI) ---
    g = si.get("growth_1m")
    f["G"] = _clip((g or 0) / 5.0)
    meta["G"] = {"raw": g, "source": "surprise_index.growth_1m"}
    infl = si.get("inflation_1m")
    f["I"] = _clip((infl or 0) / 5.0)
    meta["I"] = {"raw": infl, "source": "surprise_index.inflation_1m"}

    # --- Rates: Δ10Y yield over 1m (pp), normalized by 25bps ---
    tnx = cross.get("^TNX") or {}
    dy = None
    if tnx.get("latest") is not None and tnx.get("ret_1m") is not None:
        dy = round(tnx["latest"] * tnx["ret_1m"] / 100.0, 3)  # pp change in yield
    f["R"] = _clip((dy or 0) / 0.25)
    meta["R"] = {"raw": dy, "source": "cross_asset.^TNX Δyield(pp,1m)"}

    # --- Defensive need: late-cycle / recession from cycle_context ---
    defn = -0.5  # default: normal expansion → slight cyclical tilt
    regime_bits = []
    yc = cyc.get("yield_curve") or {}
    cregime = yc.get("regime")
    if cregime == "inverted":
        defn = +0.5
    elif cregime == "dis-inverted":
        defn = +1.0
    elif cregime == "normal":
        defn = -0.5
    if cregime:
        regime_bits.append(f"đường cong {cregime}")
    sahm = cyc.get("sahm") or {}
    if sahm.get("triggered"):
        defn = +1.5
        regime_bits.append("Sahm KÍCH HOẠT")
    elif sahm.get("value") is not None:
        defn += _clip(sahm["value"] / 0.5, 0, 0.7)  # creeping unemployment adds defensive tilt
    f["DEF"] = _clip(defn)
    meta["DEF"] = {"raw": round(defn, 2), "source": "cycle_context (Sahm+curve)",
                   "curve": cregime, "sahm": sahm.get("value")}

    # --- USD, Oil, Copper, Risk appetite (cross-asset 1m) ---
    usd = cross_ret("DX-Y.NYB")
    f["USD"] = _clip((usd or 0) / 2.0)
    meta["USD"] = {"raw": usd, "source": "cross_asset.DXY ret_1m"}

    oil = cross_ret("CL=F")
    f["OIL"] = _clip((oil or 0) / 10.0)
    meta["OIL"] = {"raw": oil, "source": "cross_asset.WTI ret_1m"}

    cu = cross_ret("HG=F")
    f["CU"] = _clip((cu or 0) / 8.0)
    meta["CU"] = {"raw": cu, "source": "cross_asset.Copper ret_1m"}

    vix = cross.get("^VIX") or {}
    vlevel = vix.get("latest")
    vret = vix.get("ret_1m")
    risk = 0.0
    if vlevel is not None:
        risk += _clip((18 - vlevel) / 6.0)          # low VIX = risk-on
    if vret is not None:
        risk += _clip(-vret / 20.0, -0.5, 0.5)       # falling VIX adds risk-on
    f["RISK"] = _clip(risk)
    meta["RISK"] = {"raw": round(risk, 2), "source": "cross_asset.VIX level+Δ",
                    "vix": vlevel}

    # --- Regime one-liner ---
    risk_word = "risk-on" if f["RISK"] > 0.3 else ("risk-off" if f["RISK"] < -0.3 else "trung tính")
    growth_word = "vượt kỳ vọng" if f["G"] > 0.2 else ("hụt kỳ vọng" if f["G"] < -0.2 else "đúng kỳ vọng")
    infl_word = "nóng hơn" if f["I"] > 0.2 else ("nguội hơn" if f["I"] < -0.2 else "đúng")
    rate_word = "lãi suất tăng" if f["R"] > 0.2 else ("lãi suất giảm" if f["R"] < -0.2 else "lãi suất đi ngang")
    summary = (f"Tăng trưởng {growth_word}, lạm phát {infl_word} kỳ vọng, {rate_word}, "
               f"{risk_word}. Chu kỳ: {', '.join(regime_bits) if regime_bits else 'n/a'}.")
    return {k: round(v, 3) for k, v in f.items()}, meta, summary


def build() -> dict:
    factors, fmeta, regime_summary = build_factors()
    sectors_lite = _load("sectors_lite.json").get("sectors", {})

    # --- macro_tilt per sector + which factors drove it ---
    macro_tilt: dict[str, float] = {}
    drivers: dict[str, list] = {}
    for tk, sens in SENS.items():
        contribs = {fac: round(factors[fac] * w, 3) for fac, w in sens.items() if factors.get(fac)}
        macro_tilt[tk] = round(sum(contribs.values()), 3)
        top = sorted(contribs.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]
        drivers[tk] = [{"factor": fac, "label": FACTOR_LABELS[fac], "contribution": val} for fac, val in top]
    macro_z = _zscores(macro_tilt)

    # --- price momentum per sector (rotation FLOW already underway) ---
    rs_1m = {tk: (sectors_lite.get(tk, {}).get("rs_1m") or 0.0) for tk in SENS}
    rs_slope = {tk: (sectors_lite.get(tk, {}).get("rs_slope") or 0.0) for tk in SENS}
    thrust = {tk: ((sectors_lite.get(tk, {}).get("breadth") or {}).get("breadth_thrust") or 0.0) for tk in SENS}
    z_rs = _zscores(rs_1m)
    z_slope = _zscores(rs_slope)
    z_thrust = _zscores(thrust)
    price_mom = {tk: round(0.5 * z_slope[tk] + 0.3 * z_thrust[tk] + 0.2 * z_rs[tk], 2) for tk in SENS}

    # --- combined rotation score (macro-weighted, momentum-confirmed) ---
    rotation = {tk: round(0.55 * macro_z[tk] + 0.45 * price_mom[tk], 3) for tk in SENS}
    ranked = sorted(SENS, key=lambda tk: rotation[tk], reverse=True)
    rot_rank = {tk: i + 1 for i, tk in enumerate(ranked)}
    tilt_rank = {tk: i + 1 for i, tk in enumerate(sorted(SENS, key=lambda t: macro_tilt[t], reverse=True))}

    def phase(tk: str) -> str:
        info = sectors_lite.get(tk, {})
        above200 = bool(info.get("above_ma200"))
        mz, pm = macro_z[tk], price_mom[tk]
        rsz, slope, thr = z_rs[tk], rs_slope[tk], thrust[tk]
        if mz >= 0.3 and pm >= 0.3 and above200:
            return "LEADING"      # macro favors + money already in + uptrend → ride it
        if mz >= 0.3 and rsz < 0.6 and (pm >= 0 or thr > 0):
            return "EARLY"        # macro favors, price not extended yet → rotation arriving
        if mz < 0 and rsz > 0.3 and (slope < 0 or thr < 0):
            return "FADING"       # macro turned, price still high but losing flow → rotation leaving
        if mz < -0.2 and pm < 0 and not above200:
            return "AVOID"
        return "NEUTRAL"

    sectors_out = {}
    for tk in SENS:
        info = sectors_lite.get(tk, {})
        br = info.get("breadth") or {}
        ph = phase(tk)
        d0 = drivers[tk][0] if drivers[tk] else None
        driver_txt = f"{d0['label']} ({d0['contribution']:+})" if d0 else "—"
        rationale = {
            "LEADING": f"Vĩ mô hậu thuẫn + dòng tiền đã vào (RS {info.get('rs_1m', 0):+.1f}%, slope {info.get('rs_slope', 0):+.1f}), trên MA200 — dẫn dắt. Driver: {driver_txt}.",
            "EARLY":   f"Vĩ mô hậu thuẫn nhưng giá CHƯA căng (RS {info.get('rs_1m', 0):+.1f}%, breadth thrust {br.get('breadth_thrust', 0):+.0f}pp) — rotation có thể đang tới. Driver: {driver_txt}.",
            "FADING":  f"Giá còn cao nhưng vĩ mô quay đầu và dòng tiền yếu đi (slope {info.get('rs_slope', 0):+.1f}, thrust {br.get('breadth_thrust', 0):+.0f}pp) — rotation rời đi. Driver: {driver_txt}.",
            "AVOID":   f"Vĩ mô bất lợi + giá yếu, dưới MA200. Driver: {driver_txt}.",
            "NEUTRAL": f"Tín hiệu hỗn hợp. Driver: {driver_txt}.",
        }[ph]
        sectors_out[tk] = {
            "name": SECTOR_NAMES[tk],
            "phase": ph,
            "rotation_score": rotation[tk],
            "rotation_rank": rot_rank[tk],
            "macro_tilt": macro_tilt[tk],
            "macro_tilt_z": macro_z[tk],
            "macro_tilt_rank": tilt_rank[tk],
            "price_momentum_z": price_mom[tk],
            "rs_1m": info.get("rs_1m"),
            "rs_slope": info.get("rs_slope"),
            "breadth_thrust": br.get("breadth_thrust"),
            "above_ma200": info.get("above_ma200"),
            "top_drivers": drivers[tk],
            "rationale": rationale,
        }

    early = [tk for tk in ranked if sectors_out[tk]["phase"] == "EARLY"]
    leading = [tk for tk in ranked if sectors_out[tk]["phase"] == "LEADING"]
    fading = [tk for tk in ranked if sectors_out[tk]["phase"] == "FADING"]

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": (sectors_lite.get("XLK", {}) or {}).get("latest_date"),
        "method": "deterministic sensitivity matrix (sector×factor); see scripts/build_sector_rotation.py",
        "regime_summary": regime_summary,
        "macro_factors": {fac: {"value": factors[fac], **fmeta[fac], "label": FACTOR_LABELS[fac]} for fac in FACTORS},
        "ranked": ranked,
        "leading": leading,
        "early_candidates": early,
        "fading": fading,
        "sectors": sectors_out,
        "tier": "daily-snapshot",
        "note": "Đây là SNAPSHOT/RADAR hằng ngày (tích lũy vào sector_rotation_history.json), "
                "KHÔNG phải verdict. 'phase' ở đây là trạng thái 1 ngày — rotation thật cần BỀN qua "
                "nhiều phiên. Verdict tất định (đã lọc persistence) nằm ở data/sector_rotation_confirmed.json "
                "do build_rotation_confirm.py sinh trong flow tuần. Agent lọc cổ phiếu đọc file confirmed đó.",
        "handoff": {"universe_file": "data/sector_holdings_latest.json"},
    }


def append_history(out: dict) -> int:
    """Append today's per-sector scores to the daily evidence series. Idempotent:
    re-running for the same as_of date REPLACES that day's entry. The weekly
    confirmation layer (build_rotation_confirm.py) reads this to measure whether a
    rotation signal PERSISTS across multiple sessions — a single day proves nothing.
    """
    as_of = out.get("as_of")
    if not as_of:
        return 0
    entry = {
        "date": as_of,
        "regime_summary": out.get("regime_summary"),
        "sectors": {
            tk: {
                "macro_tilt_z": s["macro_tilt_z"],
                "price_momentum_z": s["price_momentum_z"],
                "rotation_score": s["rotation_score"],
                "breadth_thrust": s.get("breadth_thrust"),
                "rs_slope": s.get("rs_slope"),
                "rs_1m": s.get("rs_1m"),
                "above_ma200": s.get("above_ma200"),
            }
            for tk, s in out["sectors"].items()
        },
    }
    hist = json.loads(HISTORY.read_text()) if HISTORY.exists() else {"schema_version": "1.0", "series": []}
    series = [e for e in hist.get("series", []) if e.get("date") != as_of]  # drop same-day → replace
    series.append(entry)
    series.sort(key=lambda e: e["date"])
    series = series[-HISTORY_MAX:]
    hist["series"] = series
    hist["updated_at"] = datetime.now(timezone.utc).isoformat()
    HISTORY.write_text(json.dumps(hist, indent=2, ensure_ascii=False))
    return len(series)


def main() -> int:
    out = build()
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    n_hist = append_history(out)
    print(f"Wrote {OUT}")
    print(f"History: {HISTORY.name} now has {n_hist} daily snapshot(s)")
    print(f"Regime: {out['regime_summary']}")
    print("\nRotation leaderboard (score | phase | macroZ | priceMomZ):")
    for tk in out["ranked"]:
        s = out["sectors"][tk]
        print(f"  {tk:5} {s['name'][:20]:20} {s['rotation_score']:+.2f} | {s['phase']:8} "
              f"| mz {s['macro_tilt_z']:+.2f} | pm {s['price_momentum_z']:+.2f}")
    if out["early_candidates"]:
        print(f"\n  EARLY (rotation arriving): {', '.join(out['early_candidates'])}")
    if out["leading"]:
        print(f"  LEADING (riding): {', '.join(out['leading'])}")
    if out["fading"]:
        print(f"  FADING (rotation leaving): {', '.join(out['fading'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
