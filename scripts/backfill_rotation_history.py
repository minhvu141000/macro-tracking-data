#!/usr/bin/env python3
"""One-off backfill of sector_rotation_history.json so the weekly confirmation
layer has a full ~10-session window without waiting days for it to accumulate.

Reconstructs each past session's per-sector (macro_tilt_z, price_momentum_z,
rs_1m, rs_slope) — exactly the fields build_rotation_confirm.py reads — from data
we ALREADY store as time series:
  • sectors_latest.json  rs_history (RS vs SPY, 252 sessions)  → rs_1m, rs_slope
  • cross_asset_latest.json history (252 sessions)             → R/USD/OIL/CU/RISK
  • surprise_index.json  series (per-day scores)               → G/I (rolling 30d)
  • latest raw cycle_context                                   → DEF (held constant:
        Sahm is monthly + yield-curve regime doesn't flip within a 2-week window)

Approximations vs the live daily engine (acceptable for a directional persistence
window): breadth_thrust is left None (no cheap history), so price_momentum_z drops
its 0.3·z_thrust term; DEF is constant across the window. Existing (live) entries
are PRESERVED — backfill only fills missing earlier dates.

    python scripts/backfill_rotation_history.py [n_sessions]   # default 14
"""
from __future__ import annotations

import bisect
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_sector_rotation import SENS, FACTORS, SECTOR_NAMES, _clip, _zscores, _latest_raw

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HISTORY = DATA / "sector_rotation_history.json"


def _pct(a: float, b: float) -> float | None:
    return None if not b else round((a - b) / b * 100, 2)


def _ordmap(points: list[dict]) -> tuple[list[int], list[float]]:
    """(sorted ordinals, values) from a [{date,value}] series for bisect lookup."""
    pts = sorted(points, key=lambda p: p["date"])
    ords = [date.fromisoformat(p["date"]).toordinal() for p in pts]
    vals = [p["value"] for p in pts]
    return ords, vals


def _idx_at(ords: list[int], d_ord: int) -> int | None:
    """Index of the last observation on or before d_ord."""
    i = bisect.bisect_right(ords, d_ord) - 1
    return i if i >= 0 else None


def _ret_1m(ords, vals, d_ord, n=21):
    i = _idx_at(ords, d_ord)
    if i is None or i < n:
        return None, None
    return _pct(vals[i], vals[i - n]), vals[i]


def _rolling_sum(series: list[dict], key: str, end_ord: int, days: int) -> float:
    lo = end_ord - days
    return round(sum(p.get(key, 0) or 0 for p in series
                     if lo <= date.fromisoformat(p["date"]).toordinal() <= end_ord), 2)


def _defensive_constant(cyc: dict) -> float:
    """Replicates build_sector_rotation DEF logic; held constant across the window."""
    defn = -0.5
    regime = (cyc.get("yield_curve") or {}).get("regime")
    if regime == "inverted":
        defn = 0.5
    elif regime == "dis-inverted":
        defn = 1.0
    elif regime == "normal":
        defn = -0.5
    sahm = cyc.get("sahm") or {}
    if sahm.get("triggered"):
        defn = 1.5
    elif sahm.get("value") is not None:
        defn += _clip(sahm["value"] / 0.5, 0, 0.7)
    return _clip(defn)


def main() -> int:
    n_sessions = int(sys.argv[1]) if len(sys.argv) > 1 else 14

    sectors = json.loads((DATA / "sectors_latest.json").read_text())["sectors"]
    cross = json.loads((DATA / "cross_asset_latest.json").read_text())["assets"]
    si_series = json.loads((DATA / "surprise_index.json").read_text()).get("series", [])
    cyc = (_latest_raw() or {}).get("cycle_context") or {}
    DEF = _defensive_constant(cyc)

    # Per-sector RS series (date→value) and ordinal lookup.
    rs_pts = {tk: sectors[tk].get("rs_history", []) for tk in SENS if sectors.get(tk)}
    rs_om = {tk: _ordmap(pts) for tk, pts in rs_pts.items() if pts}
    # Cross-asset ordinal lookups.
    cx_om = {tk: _ordmap(cross[tk]["history"]) for tk in cross if cross[tk].get("history")}

    # Canonical trading calendar = dates present across all sectors' RS history.
    common = None
    for tk, pts in rs_pts.items():
        ds = {p["date"] for p in pts}
        common = ds if common is None else (common & ds)
    calendar = sorted(common or [])[-n_sessions:]

    existing = {}
    if HISTORY.exists():
        for e in json.loads(HISTORY.read_text()).get("series", []):
            existing[e["date"]] = e

    def cx_ret(tk, d_ord):
        om = cx_om.get(tk)
        return (None, None) if not om else _ret_1m(om[0], om[1], d_ord)

    added = 0
    for dstr in calendar:
        if dstr in existing:
            continue  # preserve live entries
        d_ord = date.fromisoformat(dstr).toordinal()

        # --- macro factors (mirror build_sector_rotation.build_factors) ---
        f = {}
        f["G"] = _clip(_rolling_sum(si_series, "growth_score", d_ord, 30) / 5.0)
        f["I"] = _clip(_rolling_sum(si_series, "inflation_score", d_ord, 30) / 5.0)
        tnx_ret, tnx_v = cx_ret("^TNX", d_ord)
        dy = (tnx_v * tnx_ret / 100.0) if (tnx_v is not None and tnx_ret is not None) else 0.0
        f["R"] = _clip(dy / 0.25)
        f["DEF"] = DEF
        usd_ret = cx_ret("DX-Y.NYB", d_ord)[0] or 0.0
        f["USD"] = _clip(usd_ret / 2.0)
        f["OIL"] = _clip((cx_ret("CL=F", d_ord)[0] or 0.0) / 10.0)
        f["CU"] = _clip((cx_ret("HG=F", d_ord)[0] or 0.0) / 8.0)
        vix_ret, vix_v = cx_ret("^VIX", d_ord)
        risk = 0.0
        if vix_v is not None:
            risk += _clip((18 - vix_v) / 6.0)
        if vix_ret is not None:
            risk += _clip(-vix_ret / 20.0, -0.5, 0.5)
        f["RISK"] = _clip(risk)

        macro_tilt = {tk: round(sum(f[fac] * w for fac, w in SENS[tk].items()), 3) for tk in SENS}
        macro_z = _zscores(macro_tilt)

        # --- price momentum from RS history (thrust unavailable → 0 term) ---
        rs_1m, rs_slope = {}, {}
        for tk in SENS:
            om = rs_om.get(tk)
            if not om:
                rs_1m[tk] = 0.0
                rs_slope[tk] = 0.0
                continue
            i = _idx_at(om[0], d_ord)
            v = om[1]
            r1m = _pct(v[i], v[i - 21]) if (i is not None and i >= 21) else 0.0
            r1w = _pct(v[i], v[i - 5]) if (i is not None and i >= 5) else 0.0
            rs_1m[tk] = r1m or 0.0
            rs_slope[tk] = round((r1w or 0.0) - (r1m or 0.0) * (5 / 21), 2)
        z_rs = _zscores(rs_1m)
        z_slope = _zscores(rs_slope)
        price_mom = {tk: round(0.5 * z_slope[tk] + 0.2 * z_rs[tk], 2) for tk in SENS}

        entry = {
            "date": dstr,
            "regime_summary": "(backfill — DEF/cycle giữ hằng số, breadth_thrust=None)",
            "sectors": {
                tk: {
                    "macro_tilt_z": macro_z[tk],
                    "price_momentum_z": price_mom[tk],
                    "rotation_score": round(0.55 * macro_z[tk] + 0.45 * price_mom[tk], 3),
                    "breadth_thrust": None,
                    "rs_slope": rs_slope[tk],
                    "rs_1m": rs_1m[tk],
                    "above_ma200": None,
                }
                for tk in SENS
            },
        }
        existing[dstr] = entry
        added += 1

    series = sorted(existing.values(), key=lambda e: e["date"])[-90:]
    HISTORY.write_text(json.dumps(
        {"schema_version": "1.0", "updated_at": datetime.now(timezone.utc).isoformat(), "series": series},
        indent=2, ensure_ascii=False))
    print(f"Backfilled {added} session(s); history now {len(series)} entries "
          f"({series[0]['date']} → {series[-1]['date']}). DEF const={DEF} (curve="
          f"{(cyc.get('yield_curve') or {}).get('regime')}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
