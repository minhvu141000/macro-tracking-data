#!/usr/bin/env python3
"""MONTHLY rotation FORECAST engine — horizon ~1 tháng (21 phiên).

Tầng thứ 3 trên trục thời gian, song song với 2 tầng có sẵn:
  - build_sector_rotation.py  → DAILY radar (1 phiên, nhiễu)
  - build_rotation_confirm.py → WEEKLY verdict (persistence 10 phiên)
  - build_monthly_rotation.py → MONTHLY forecast (persistence 21 phiên)  ← file này

Mục tiêu: dự báo nhóm ngành nào sẽ NHẬN dòng tiền trong THÁNG TỚI, làm ĐẦU VÀO
cho fundamental agent lọc cổ phiếu trong sector đó.

Đọc:
  - data/sector_rotation_history.json  (~21 phiên macro_tilt_z / price_momentum_z / rotation_score)
  - data/sector_rotation_confirmed.json (money_flow + composite + regime hiện tại)
  - data/sector_holdings_latest.json   (universe cổ phiếu/sector — handoff)

Ghi 3 đầu ra TÁCH BIỆT theo yêu cầu:
  1. AGENT (sâu, KHÔNG lên dashboard):
       data/monthly/rotation_forecast_<TARGET_MONTH>.json  — máy đọc
       data/monthly/rotation_forecast_<TARGET_MONTH>.md    — phân tích sâu cho agent
  2. DASHBOARD (chỉ biểu đồ):
       data/monthly_rotation_forecast_latest.json — gọn, build_dashboard.py render bar chart

    python scripts/build_monthly_rotation.py

Logic tất định (không LLM): 3 trục — VĨ MÔ (macro_tilt persistence) · DÒNG TIỀN
(MFI vs SPY) · GIÁ (rotation_score/RS/MA200) — tổng hợp thành forecast_phase + score.
Độ tin tăng dần khi tích lũy nhiều phiên DAILY thật (xem rotation_engine_scorecard).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_sector_rotation import SECTOR_NAMES
from build_rotation_confirm import _trend

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HISTORY = DATA / "sector_rotation_history.json"
CONFIRMED = DATA / "sector_rotation_confirmed.json"
HOLDINGS = DATA / "sector_holdings_latest.json"
OUT_DASH = DATA / "monthly_rotation_forecast_latest.json"
MONTHLY_DIR = DATA / "monthly"

# --- Tunable monthly-horizon params ---
MONTH_WINDOW = 21       # phiên ~ 1 tháng giao dịch
MIN_FULL = 15           # < ngần này phiên → cap conviction (chưa đủ 1 tháng dữ liệu)
MACRO_THR = 0.3         # macro_tilt_z > thr = vĩ mô hậu thuẫn phiên đó
POS_FRAC = 0.6          # tỷ lệ phiên cần macro-dương để coi là "bền"
# trọng số tổng hợp forecast_score (tài liệu hoá để chỉnh)
W_BASE, W_TREND, W_FLOW = 1.0, 0.4, 0.2

PHASE_COLORS = {
    "INFLOW_LIKELY": "#4ade80", "FORMING": "#2dd4bf", "NEUTRAL": "#8b96a3",
    "OUTFLOW_LIKELY": "#fbbf24", "AVOID": "#f87171",
}
PHASE_ORDER = {"INFLOW_LIKELY": 4, "FORMING": 3, "NEUTRAL": 2, "OUTFLOW_LIKELY": 1, "AVOID": 0}


def _next_month_str(today: date) -> str:
    y, m = today.year, today.month
    return f"{y + 1}-01" if m == 12 else f"{y}-{m + 1:02d}"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def forecast(series: list[dict], confirmed: dict, holdings: dict) -> dict:
    window = series[-MONTH_WINDOW:]
    n = len(window)
    latest = window[-1] if window else {}
    conf_secs = confirmed.get("sectors", {})
    hold = holdings.get("holdings", {})

    macro_need = round(POS_FRAC * n)
    sectors_out: dict[str, dict] = {}

    for tk in SECTOR_NAMES:
        mz = [e["sectors"].get(tk, {}).get("macro_tilt_z", 0.0) for e in window]
        pm = [e["sectors"].get(tk, {}).get("price_momentum_z", 0.0) for e in window]
        rsc = [e["sectors"].get(tk, {}).get("rotation_score", 0.0) for e in window]
        last = latest.get("sectors", {}).get(tk, {})

        macro_pos = sum(1 for z in mz if z > MACRO_THR)
        macro_neg = sum(1 for z in mz if z < -MACRO_THR)
        mom_pos = sum(1 for z in pm if z > 0)
        mom_neg = sum(1 for z in pm if z < 0)
        tilt_trend = _trend(mz)
        mom_trend = _trend(pm)
        score_trend = _trend(rsc)
        base = round(sum(rsc) / n, 3) if n else 0.0
        rs_1m = last.get("rs_1m") or 0.0
        above_ma200 = last.get("above_ma200")

        # money flow (snapshot hiện tại từ confirmed)
        mf = (conf_secs.get(tk, {}) or {}).get("money_flow", {}) or {}
        mfi_vs_spy = mf.get("mfi_vs_spy", 0.0)
        flow_signal = mf.get("flow_signal")
        inflow = flow_signal in ("STRONG_INFLOW", "INFLOW")
        outflow = flow_signal in ("STRONG_OUTFLOW", "OUTFLOW")

        forecast_score = round(W_BASE * base + W_TREND * score_trend
                               + W_FLOW * (mfi_vs_spy / 30.0), 3)

        # --- forecast_phase (tất định) ---
        macro_strong = macro_pos >= macro_need
        macro_weak = macro_neg >= macro_need
        if macro_strong and (mom_pos >= 0.5 * n or inflow) and score_trend >= -0.1:
            phase = "INFLOW_LIKELY"
        elif macro_strong:
            phase = "FORMING"                       # vĩ mô bền nhưng tiền/giá chưa xác nhận
        elif macro_weak and outflow and rs_1m < 0:
            phase = "AVOID"
        elif macro_weak and (outflow or mom_neg >= 0.5 * n):
            phase = "OUTFLOW_LIKELY"
        else:
            phase = "NEUTRAL"

        # --- confidence ---
        axes_pos = sum([macro_strong, inflow, (rs_1m > 0 and bool(above_ma200))])
        axes_neg = sum([macro_weak, outflow, (rs_1m < 0)])
        agree = max(axes_pos, axes_neg)
        if n < MIN_FULL:
            conf = "LOW"                            # chưa đủ ~1 tháng dữ liệu
        elif agree >= 3:
            conf = "HIGH"
        elif agree == 2:
            conf = "MED"
        else:
            conf = "LOW"

        # --- universe cổ phiếu cho agent (chỉ sector đáng săn) ---
        stock_universe = []
        if phase in ("INFLOW_LIKELY", "FORMING"):
            cands = [h for h in hold.get(tk, [])
                     if (h.get("rs_1m") or 0) > 0 and h.get("above_ma50")]
            cands.sort(key=lambda h: h.get("rs_1m") or 0, reverse=True)
            stock_universe = [{"ticker": h["ticker"], "rs_1m": h.get("rs_1m"),
                               "ret_1m": h.get("ret_1m"), "above_ma200": h.get("above_ma200")}
                              for h in cands[:10]]

        rationale = {
            "INFLOW_LIKELY": f"Vĩ mô hậu thuẫn bền {macro_pos}/{n} phiên + dòng tiền/giá xác nhận "
                             f"(mom {mom_pos}/{n}, MFI vs SPY {mfi_vs_spy:+.1f}, trend {score_trend:+}) "
                             f"→ KHẢ NĂNG NHẬN dòng tiền tháng tới. Sector để fundamental agent săn cổ phiếu.",
            "FORMING": f"Vĩ mô bền ({macro_pos}/{n}) nhưng dòng tiền/giá chưa theo "
                       f"(mom {mom_pos}/{n}, MFI vs SPY {mfi_vs_spy:+.1f}) → ĐANG HÌNH THÀNH, "
                       f"canh vào sớm khi giá vượt MA / dòng tiền chuyển dương.",
            "OUTFLOW_LIKELY": f"Vĩ mô yếu ({macro_pos}/{n}) + dòng tiền/giá yếu "
                              f"(mom {mom_pos}/{n}, MFI vs SPY {mfi_vs_spy:+.1f}) → có khả năng RA tiền.",
            "AVOID": f"Vĩ mô yếu bền + dòng tiền ra + RS âm ({rs_1m:+.1f}%) → tránh.",
            "NEUTRAL": f"Không có lợi thế/bất lợi bền (macro {macro_pos}/{n}, mom {mom_pos}/{n}).",
        }[phase]

        sectors_out[tk] = {
            "name": SECTOR_NAMES[tk],
            "forecast_phase": phase,
            "confidence": conf,
            "forecast_score": forecast_score,
            "axes": {
                "macro": {"pos_days": macro_pos, "neg_days": macro_neg, "n": n,
                          "tilt_trend": tilt_trend, "strong": macro_strong},
                "flow": {"mfi_vs_spy": mfi_vs_spy, "flow_signal": flow_signal},
                "price": {"rs_1m": last.get("rs_1m"), "above_ma200": above_ma200,
                          "mom_pos_days": mom_pos, "mom_trend": mom_trend},
            },
            "avg_rotation_score": base,
            "score_trend": score_trend,
            "rationale": rationale,
            "stock_universe": stock_universe,
            "_order": PHASE_ORDER[phase],
        }

    ranked = sorted(SECTOR_NAMES,
                    key=lambda tk: (sectors_out[tk]["_order"], sectors_out[tk]["forecast_score"]),
                    reverse=True)
    for tk in sectors_out:
        sectors_out[tk].pop("_order", None)

    def bucket(name):
        return [tk for tk in ranked if sectors_out[tk]["forecast_phase"] == name]

    return {
        "sectors": sectors_out, "ranked": ranked, "n_sessions": n,
        "as_of_latest": latest.get("date"),
        "as_of_oldest": window[0].get("date") if window else None,
        "regime_summary": confirmed.get("regime_summary") or latest.get("regime_summary"),
        "buckets": {
            "inflow_likely": bucket("INFLOW_LIKELY"), "forming": bucket("FORMING"),
            "neutral": bucket("NEUTRAL"), "outflow_likely": bucket("OUTFLOW_LIKELY"),
            "avoid": bucket("AVOID"),
        },
    }


def write_agent_json(fc: dict, target_month: str) -> Path:
    out = {
        "schema_version": "1.0",
        "horizon": "monthly",
        "target_month": target_month,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_sessions": fc["n_sessions"],
        "as_of": fc["as_of_latest"],
        "window_from": fc["as_of_oldest"],
        "regime_summary": fc["regime_summary"],
        "params": {"MONTH_WINDOW": MONTH_WINDOW, "MACRO_THR": MACRO_THR,
                   "POS_FRAC": POS_FRAC, "weights": {"base": W_BASE, "trend": W_TREND, "flow": W_FLOW}},
        "data_quality": {
            "n_sessions": fc["n_sessions"],
            "full_month_window": MONTH_WINDOW,
            "note": ("Độ tin tăng dần theo số phiên DAILY thật. Tham chiếu "
                     "data/monthly/rotation_engine_scorecard.md để biết edge dự báo hiện tại "
                     "(hiện còn nhỏ/backfill → coi như giả thuyết, chưa phải kết luận)."),
        },
        "ranked": fc["ranked"],
        "buckets": fc["buckets"],
        "sectors": fc["sectors"],
        "handoff": {
            "consumer": "fundamental-stock-picker agent",
            "instruction": ("Săn cổ phiếu trong sector forecast_phase = INFLOW_LIKELY (ưu tiên) "
                            "và FORMING (vào sớm). Lấy danh sách ở sectors[<tk>].stock_universe "
                            "(đã lọc rs_1m>0 + above_ma50), rồi chấm fundamental (tăng trưởng EPS/doanh thu, "
                            "định giá, biên LN, FCF, nợ). BỎ QUA OUTFLOW_LIKELY/AVOID. "
                            "Tôn trọng confidence: HIGH = vào mạnh, MED = thăm dò, LOW = chỉ watchlist."),
            "universe_file": "data/sector_holdings_latest.json",
        },
    }
    MONTHLY_DIR.mkdir(parents=True, exist_ok=True)
    p = MONTHLY_DIR / f"rotation_forecast_{target_month}.json"
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return p


def write_agent_md(fc: dict, target_month: str) -> Path:
    s = fc["sectors"]
    lines = [
        f"# Dự báo luân chuyển dòng tiền — Tháng {target_month}",
        "",
        "> **File cho AI agent (fundamental stock-picker) — KHÔNG hiển thị trên dashboard.**",
        f"> Horizon: tháng tới · Cửa sổ: {fc['n_sessions']} phiên ({fc['as_of_oldest']} → {fc['as_of_latest']}).",
        f"> Regime: {fc['regime_summary']}",
        "",
        "⚠️ **Độ tin:** engine dự báo dựa trên persistence 3 trục (vĩ mô · dòng tiền · giá). "
        "Edge dự báo hiện CHƯA kiểm chứng (mẫu nhỏ/backfill — xem `rotation_engine_scorecard.md`). "
        "Dùng như xếp hạng ưu tiên + giả thuyết, KHÔNG phải tín hiệu chắc chắn.",
        "",
        "## Xếp hạng dự báo (cao → thấp)",
        "",
        "| # | Sector | ETF | Phase | Conf | Score | Vĩ mô | Dòng tiền (MFI vs SPY) | Giá (RS 1M) |",
        "|---|--------|-----|-------|------|-------|-------|------------------------|-------------|",
    ]
    for i, tk in enumerate(fc["ranked"], 1):
        v = s[tk]; ax = v["axes"]
        lines.append(
            f"| {i} | {v['name']} | {tk} | **{v['forecast_phase']}** | {v['confidence']} | "
            f"{v['forecast_score']:+.2f} | {ax['macro']['pos_days']}/{ax['macro']['n']} | "
            f"{ax['flow']['mfi_vs_spy']:+.1f} {ax['flow']['flow_signal'] or '—'} | "
            f"{ax['price']['rs_1m'] if ax['price']['rs_1m'] is not None else '—'}% |"
        )

    inflow = fc["buckets"]["inflow_likely"] + fc["buckets"]["forming"]
    lines += ["", "## Sector để fundamental agent SĂN cổ phiếu", ""]
    if not inflow:
        lines.append("_Chưa có sector nào INFLOW_LIKELY/FORMING._")
    for tk in inflow:
        v = s[tk]
        lines += [f"### {v['name']} ({tk}) — {v['forecast_phase']} · conf {v['confidence']}",
                  f"{v['rationale']}", ""]
        if v["stock_universe"]:
            lines.append("**Universe (đã lọc rs_1m>0 + above_ma50, sort RS giảm dần):**")
            lines.append("| Ticker | RS 1M | Ret 1M | >MA200 |")
            lines.append("|--------|-------|--------|--------|")
            for h in v["stock_universe"]:
                lines.append(f"| {h['ticker']} | {h['rs_1m']}% | {h.get('ret_1m')}% | "
                             f"{'✓' if h.get('above_ma200') else '✗'} |")
        else:
            lines.append("_Không có cổ phiếu nào trong universe đạt rs_1m>0 + above_ma50._")
        lines.append("")

    avoid = fc["buckets"]["outflow_likely"] + fc["buckets"]["avoid"]
    if avoid:
        lines += ["## Sector NÉ (outflow/avoid)", ""]
        for tk in avoid:
            lines.append(f"- **{s[tk]['name']} ({tk})** — {s[tk]['forecast_phase']}: {s[tk]['rationale']}")
        lines.append("")

    lines += [
        "## Hướng dẫn cho agent",
        "1. Ưu tiên INFLOW_LIKELY → FORMING (theo `ranked`).",
        "2. Lấy `stock_universe` mỗi sector → chấm fundamental (tăng trưởng EPS/doanh thu, định giá P/E-P/S, biên LN, FCF, nợ).",
        "3. Tôn trọng `confidence`: HIGH=vào mạnh · MED=thăm dò · LOW=watchlist.",
        "4. BỎ QUA outflow_likely/avoid.",
        "5. Dữ liệu máy đọc đầy đủ: `rotation_forecast_" + target_month + ".json`.",
    ]
    MONTHLY_DIR.mkdir(parents=True, exist_ok=True)
    p = MONTHLY_DIR / f"rotation_forecast_{target_month}.md"
    p.write_text("\n".join(lines) + "\n")
    return p


def write_dashboard_json(fc: dict, target_month: str) -> Path:
    s = fc["sectors"]
    items = [{
        "ticker": tk, "name": s[tk]["name"], "forecast_score": s[tk]["forecast_score"],
        "phase": s[tk]["forecast_phase"], "color": PHASE_COLORS[s[tk]["forecast_phase"]],
        "confidence": s[tk]["confidence"],
    } for tk in fc["ranked"]]
    out = {"schema_version": "1.0", "target_month": target_month,
           "generated_at": datetime.now(timezone.utc).isoformat(),
           "as_of": fc["as_of_latest"], "n_sessions": fc["n_sessions"],
           "regime_summary": fc["regime_summary"], "items": items}
    OUT_DASH.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return OUT_DASH


def main() -> int:
    if not HISTORY.exists():
        print(f"No {HISTORY.name} — chạy build_sector_rotation.py (daily) để tích lũy.")
        return 0
    series = json.loads(HISTORY.read_text()).get("series", [])
    series.sort(key=lambda e: e["date"])
    if not series:
        print("rotation_history rỗng.")
        return 0

    confirmed = _load(CONFIRMED)
    holdings = _load(HOLDINGS)
    target_month = _next_month_str(date.today())

    fc = forecast(series, confirmed, holdings)
    pj = write_agent_json(fc, target_month)
    pm = write_agent_md(fc, target_month)
    pd = write_dashboard_json(fc, target_month)

    print(f"Forecast tháng {target_month} | cửa sổ {fc['n_sessions']} phiên "
          f"({fc['as_of_oldest']} → {fc['as_of_latest']})")
    print(f"  AGENT json: {pj.name} | AGENT md: {pm.name} | DASHBOARD: {pd.name}")
    print("\n  Xếp hạng dự báo:")
    for tk in fc["ranked"]:
        v = fc["sectors"][tk]
        print(f"    {tk:5} {v['name'][:20]:20} {v['forecast_phase']:15} {v['confidence']:4} "
              f"score={v['forecast_score']:+.2f}")
    if fc["buckets"]["inflow_likely"]:
        print("  INFLOW_LIKELY:", ", ".join(fc["buckets"]["inflow_likely"]))
    if fc["buckets"]["forming"]:
        print("  FORMING:", ", ".join(fc["buckets"]["forming"]))
    if fc["n_sessions"] < MIN_FULL:
        print(f"  ⚠ Mới {fc['n_sessions']} phiên (<{MIN_FULL}) → conviction bị cap, cần chạy daily thêm.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
