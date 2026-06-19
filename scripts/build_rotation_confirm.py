#!/usr/bin/env python3
"""Weekly CONFIRMATION layer for sector rotation — the deterministic verdict.

Rotation is a multi-session phenomenon: a single day's macro→sector snapshot is
noise. This script reads the daily evidence series (sector_rotation_history.json,
appended by build_sector_rotation.py) over a trailing window and keeps only signals
that PERSIST — that's what distinguishes real capital rotation from a one-day pop.

For each sector over the last WINDOW sessions it measures:
  • macro_pos_days  — sessions the macro backdrop favored it (macro_tilt_z > thr)
  • mom_pos_days    — sessions money was already flowing in (price_momentum_z > 0)
  • tilt_trend / mom_trend — are those axes RISING across the window?
  • thrust_mean     — average breadth thrust (sustained, not a single spike)

Confirmed verdict (deterministic):
  CONFIRMED_IN   macro persistent + flow persistent + not deteriorating → ride/buy
  EARLY_FORMING  macro persistent, flow still building → prime hunting ground
  FADING         macro gone, price still elevated, flow rolling over → reduce
  AVOID          macro & flow both persistently weak
  NEUTRAL        mixed / no persistent edge

Output: data/sector_rotation_confirmed.json  — THE handoff the stock-picking agent
reads (sector verdict) alongside data/sector_holdings_latest.json (name universe).

    python scripts/build_rotation_confirm.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_sector_rotation import SECTOR_NAMES  # single source of truth for names

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HISTORY = DATA / "sector_rotation_history.json"
OUT = DATA / "sector_rotation_confirmed.json"
SECTORS_LITE = DATA / "sectors_lite.json"

# --- Tunable persistence parameters ---
WINDOW = 10          # trailing sessions to judge (~2 weeks)
MIN_DAYS = 4         # below this we cannot confirm anything → INSUFFICIENT_HISTORY
MACRO_THR = 0.3      # macro_tilt_z above this = "macro favors sector" that day
MACRO_POS_FRAC = 0.6 # fraction of window that must be macro-positive to confirm
MOM_POS_FRAC = 0.5   # fraction that must be momentum-positive to confirm flow


def _trend(vals: list[float]) -> float:
    """avg(last third) − avg(first third): + = rising across the window."""
    n = len(vals)
    if n < 2:
        return 0.0
    k = max(1, n // 3)
    return round(sum(vals[-k:]) / k - sum(vals[:k]) / k, 2)


def confirm(series: list[dict]) -> dict:
    """Pure function: daily evidence series → confirmed per-sector verdict.
    `series` is sorted ascending by date; uses the last WINDOW entries.
    """
    window = series[-WINDOW:]
    n = len(window)
    latest = window[-1] if window else {}
    insufficient = n < MIN_DAYS

    macro_need = max(MIN_DAYS - 1, round(MACRO_POS_FRAC * n))
    mom_need = max(MIN_DAYS - 2, round(MOM_POS_FRAC * n))

    sectors_out: dict[str, dict] = {}
    for tk in SECTOR_NAMES:
        mz = [e["sectors"].get(tk, {}).get("macro_tilt_z", 0.0) for e in window]
        pm = [e["sectors"].get(tk, {}).get("price_momentum_z", 0.0) for e in window]
        thr = [e["sectors"].get(tk, {}).get("breadth_thrust") for e in window]
        thr = [t for t in thr if t is not None]
        last = latest.get("sectors", {}).get(tk, {})

        macro_pos = sum(1 for z in mz if z > MACRO_THR)
        macro_neg = sum(1 for z in mz if z < -MACRO_THR)
        mom_pos = sum(1 for z in pm if z > 0)
        mom_neg = sum(1 for z in pm if z < 0)
        tilt_trend = _trend(mz)
        mom_trend = _trend(pm)
        thrust_mean = round(sum(thr) / len(thr), 1) if thr else None
        rs_1m = last.get("rs_1m") or 0.0

        if insufficient:
            phase = "INSUFFICIENT_HISTORY"
            conf = "n/a"
        elif macro_pos >= macro_need and mom_pos >= mom_need and tilt_trend >= -0.15 and mom_trend >= -0.3:
            phase = "CONFIRMED_IN"
            conf = "HIGH" if macro_pos >= 0.7 * n else "MED"
        elif macro_pos >= macro_need:
            phase = "EARLY_FORMING"           # macro bền, dòng tiền chưa xác nhận
            conf = "MED" if mom_trend > 0 else "LOW"
        elif macro_neg >= macro_need and rs_1m > 0 and mom_trend < 0:
            phase = "FADING"                  # vĩ mô âm bền, giá còn cao, momentum lăn xuống
            conf = "MED"
        elif macro_neg >= macro_need and mom_neg >= mom_need:
            phase = "AVOID"                   # vĩ mô âm bền + dòng tiền âm bền
            conf = "MED"
        else:
            phase = "NEUTRAL"                 # không có lợi thế/bất lợi BỀN nào
            conf = "LOW"

        rationale = {
            "CONFIRMED_IN": f"Vĩ mô hậu thuẫn {macro_pos}/{n} phiên + dòng tiền vào {mom_pos}/{n}, xu hướng còn lên (tilt {tilt_trend:+}, mom {mom_trend:+}) — rotation đã XÁC NHẬN.",
            "EARLY_FORMING": f"Vĩ mô hậu thuẫn bền ({macro_pos}/{n}) nhưng dòng tiền mới {mom_pos}/{n} (mom trend {mom_trend:+}) — đang HÌNH THÀNH, ưu tiên theo dõi/săn sớm.",
            "FADING": f"Vĩ mô chỉ còn {macro_pos}/{n} phiên, giá vẫn cao (RS {rs_1m:+.1f}%) nhưng momentum lăn xuống ({mom_trend:+}) — rotation RỜI ĐI.",
            "AVOID": f"Vĩ mô yếu ({macro_pos}/{n}) + dòng tiền yếu ({mom_pos}/{n}) bền — tránh.",
            "NEUTRAL": f"Không có lợi thế bền (macro {macro_pos}/{n}, mom {mom_pos}/{n}).",
            "INSUFFICIENT_HISTORY": f"Mới {n} phiên trong lịch sử (cần ≥{MIN_DAYS}) — chưa đủ để xác nhận persistence. Chạy daily thêm vài ngày.",
        }[phase]

        # Rank weight to order the handoff: confirmed_in highest, then early.
        order = {"CONFIRMED_IN": 4, "EARLY_FORMING": 3, "NEUTRAL": 2, "FADING": 1, "AVOID": 0,
                 "INSUFFICIENT_HISTORY": 2}[phase]
        sectors_out[tk] = {
            "name": SECTOR_NAMES[tk],
            "confirmed_phase": phase,
            "confidence": conf,
            "_order": order,
            "persistence": {
                "n_days": n,
                "macro_pos_days": macro_pos,
                "mom_pos_days": mom_pos,
                "tilt_trend": tilt_trend,
                "mom_trend": mom_trend,
                "thrust_mean": thrust_mean,
            },
            "latest": {
                "rs_1m": last.get("rs_1m"),
                "breadth_thrust": last.get("breadth_thrust"),
                "above_ma200": last.get("above_ma200"),
            },
            "rationale": rationale,
        }

    ranked = sorted(SECTOR_NAMES, key=lambda tk: (sectors_out[tk]["_order"],
                    sectors_out[tk]["persistence"]["macro_pos_days"]), reverse=True)
    for tk in sectors_out:
        sectors_out[tk].pop("_order", None)

    def bucket(name: str) -> list:
        return [tk for tk in ranked if sectors_out[tk]["confirmed_phase"] == name]

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tier": "weekly-confirmed",
        "window_days": n,
        "as_of_latest": latest.get("date"),
        "as_of_oldest": window[0].get("date") if window else None,
        "params": {"WINDOW": WINDOW, "MACRO_THR": MACRO_THR,
                   "MACRO_POS_FRAC": MACRO_POS_FRAC, "MOM_POS_FRAC": MOM_POS_FRAC},
        "regime_summary": latest.get("regime_summary"),
        "insufficient_history": insufficient,
        "ranked": ranked,
        "confirmed_in": bucket("CONFIRMED_IN"),
        "early_forming": bucket("EARLY_FORMING"),
        "fading": bucket("FADING"),
        "avoid": bucket("AVOID"),
        "sectors": sectors_out,
        "handoff": {
            "universe_file": "data/sector_holdings_latest.json",
            "note": "VERDICT cho agent lọc cổ phiếu. Săn cổ phiếu trong sector "
                    "confirmed_in (đu theo) + early_forming (vào sớm); lấy holdings "
                    "sector đó trong universe_file, lọc theo rs_1m + above_ma50. "
                    "Bỏ qua fading/avoid.",
        },
    }


def _load_money_flow() -> dict[str, dict]:
    """Load money_flow block from sectors_lite.json for each SPDR ETF.
    Returns {ticker: money_flow_dict} or {} if file missing/stale.
    """
    if not SECTORS_LITE.exists():
        return {}
    try:
        data = json.loads(SECTORS_LITE.read_text())
        out = {}
        for tk, info in data.get("sectors", {}).items():
            mf = info.get("money_flow")
            if mf:
                out[tk] = mf
        return out
    except Exception:
        return {}


def _composite_signal(confirmed_phase: str, flow_signal: str | None) -> str:
    """Combine macro-persistence verdict with volume flow signal.

    Rules (deterministic, no LLM):
    - CONFIRMED_IN + STRONG_INFLOW/INFLOW → RIDE (highest conviction)
    - CONFIRMED_IN + NEUTRAL              → HOLD
    - CONFIRMED_IN + OUTFLOW/STRONG_OUTFLOW → MONITOR (rotation possibly peaking)
    - EARLY_FORMING + STRONG_INFLOW/INFLOW  → ACCUMULATE (macro forming + flow confirming)
    - EARLY_FORMING + NEUTRAL/OUTFLOW       → WATCH
    - FADING + OUTFLOW/STRONG_OUTFLOW       → EXIT (double confirmation to sell)
    - AVOID + any                           → AVOID
    - NEUTRAL + STRONG_INFLOW               → WATCH_FLOW (price not confirmed yet)
    - everything else                       → HOLD
    """
    if confirmed_phase == "AVOID":
        return "AVOID"
    if confirmed_phase == "CONFIRMED_IN":
        if flow_signal in ("STRONG_INFLOW", "INFLOW"):
            return "RIDE"
        if flow_signal in ("OUTFLOW", "STRONG_OUTFLOW"):
            return "MONITOR"
        return "HOLD"
    if confirmed_phase == "EARLY_FORMING":
        if flow_signal in ("STRONG_INFLOW", "INFLOW"):
            return "ACCUMULATE"
        return "WATCH"
    if confirmed_phase == "FADING":
        if flow_signal in ("OUTFLOW", "STRONG_OUTFLOW"):
            return "EXIT"
        return "REDUCE"
    if confirmed_phase == "NEUTRAL" and flow_signal == "STRONG_INFLOW":
        return "WATCH_FLOW"
    return "HOLD"


def main() -> int:
    if not HISTORY.exists():
        print(f"No {HISTORY.name} yet — chạy build_sector_rotation.py (daily) trước để tích lũy.")
        return 0
    series = json.loads(HISTORY.read_text()).get("series", [])
    series.sort(key=lambda e: e["date"])
    out = confirm(series)

    # Merge volume money flow from sectors_lite.json (current week snapshot)
    mf_data = _load_money_flow()
    if mf_data:
        out["money_flow_as_of"] = json.loads(SECTORS_LITE.read_text()).get("fetched_at", "")[:10]
        for tk, sector in out.get("sectors", {}).items():
            mf = mf_data.get(tk, {})
            if mf:
                sector["money_flow"] = mf
                sector["composite_signal"] = _composite_signal(
                    sector["confirmed_phase"], mf.get("flow_signal")
                )

    # Print money flow summary
    if mf_data:
        print("\n  Money Flow (MFI 5D vs SPY):")
        ranked_mf = sorted(
            [(tk, mf_data[tk]) for tk in mf_data],
            key=lambda x: x[1].get("mfi_vs_spy", 0), reverse=True
        )
        for tk, mf in ranked_mf:
            sig = mf.get("flow_signal", "?")
            vs = mf.get("mfi_vs_spy", 0)
            comp = out["sectors"].get(tk, {}).get("composite_signal", "?")
            print(f"    {tk:5} MFI_vs_SPY={vs:+5.1f}  {sig:18}  → {comp}")

    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"Wrote {OUT}  (window={out['window_days']} phiên: {out['as_of_oldest']} → {out['as_of_latest']})")
    if out["insufficient_history"]:
        print("  ⚠ INSUFFICIENT_HISTORY — cần thêm vài ngày daily snapshot để xác nhận persistence.")
        return 0
    print(f"  Regime: {out['regime_summary']}")
    print("\n  Confirmed verdict:")
    for tk in out["ranked"]:
        s = out["sectors"][tk]
        p = s["persistence"]
        print(f"    {tk:5} {s['name'][:20]:20} {s['confirmed_phase']:18} {s['confidence']:4} "
              f"(macro {p['macro_pos_days']}/{p['n_days']}, mom {p['mom_pos_days']}/{p['n_days']})")
    for label, key in [("CONFIRMED IN", "confirmed_in"), ("EARLY FORMING", "early_forming"),
                       ("FADING", "fading"), ("AVOID", "avoid")]:
        if out[key]:
            print(f"  {label}: {', '.join(out[key])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
