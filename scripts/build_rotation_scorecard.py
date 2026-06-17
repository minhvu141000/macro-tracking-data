#!/usr/bin/env python3
"""Feedback loop for the sector-rotation ENGINE — does its score predict the future?

The monthly scorecard grades the LLM's prose calls. This grades the deterministic
engine itself: for every daily snapshot in sector_rotation_history.json, look
FORWARD N sessions and measure each sector's realized relative strength vs SPY
(from rs_history). Then ask:
  • Directional hit rate — when rotation_score was bullish (>thr), did the sector
    actually out-perform SPY over the next N days? And bearish → under-perform?
  • Edge (the money metric) — average forward RS of the top-3 ranked sectors minus
    the bottom-3, per day, averaged. >0 means the ranking adds value.

No look-ahead: the score at day D uses data ≤ D; forward RS is the independent
D→D+N window. So this is a valid (if short) backtest that works on the current
(mostly back-filled) history immediately, and sharpens as real daily snapshots
accumulate.

Output: data/monthly/rotation_engine_scorecard.md  (+ json sibling)

    python scripts/build_rotation_scorecard.py
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HISTORY = DATA / "sector_rotation_history.json"
SECTORS_FULL = DATA / "sectors_latest.json"   # has rs_history (RS-vs-SPY index series)
OUT_MD = DATA / "monthly" / "rotation_engine_scorecard.md"
OUT_JSON = DATA / "rotation_engine_scorecard.json"

HORIZONS = [5, 10]      # forward sessions to evaluate (≈1wk, 2wk)
BULL_THR = 0.3          # rotation_score above → engine is bullish that day
BEAR_THR = -0.3         # below → bearish
HIT_RS = 0.5            # forward RS (%) needed to count as right direction


def _rs_series() -> dict[str, dict[str, float]]:
    """Per sector: {date_str: rs_index_value} from sectors_latest.json rs_history."""
    sectors = json.loads(SECTORS_FULL.read_text()).get("sectors", {})
    out = {}
    for tk, info in sectors.items():
        out[tk] = {p["date"]: p["value"] for p in info.get("rs_history", [])}
    return out


def _forward_rs(series: dict[str, float], dates_sorted: list[str], d: str, n: int) -> float | None:
    """% change of the RS-vs-SPY index from day d to n sessions later. + = out-performed SPY."""
    if d not in series:
        return None
    i = dates_sorted.index(d)
    j = i + n
    if j >= len(dates_sorted):
        return None
    v0, v1 = series[dates_sorted[i]], series[dates_sorted[j]]
    return round((v1 - v0) / v0 * 100, 2) if v0 else None


def evaluate() -> dict:
    hist = json.loads(HISTORY.read_text()).get("series", [])
    hist.sort(key=lambda e: e["date"])
    rs = _rs_series()
    # per-sector sorted date axis for forward lookup
    axis = {tk: sorted(s.keys()) for tk, s in rs.items()}

    results = {}
    for n in HORIZONS:
        hits = misses = pushes = 0
        spreads = []           # daily top3 − bottom3 forward RS
        bull_fwd, bear_fwd = [], []
        scored_days = 0
        for entry in hist:
            d = entry["date"]
            day_rows = []  # (sector, score, fwd_rs)
            for tk, sd in entry.get("sectors", {}).items():
                score = sd.get("rotation_score")
                if tk not in rs:
                    continue
                fwd = _forward_rs(rs[tk], axis[tk], d, n)
                if fwd is None or score is None:
                    continue
                day_rows.append((tk, score, fwd))
                # directional scoring
                if score > BULL_THR:
                    bull_fwd.append(fwd)
                    if fwd > HIT_RS: hits += 1
                    elif fwd < -HIT_RS: misses += 1
                    else: pushes += 1
                elif score < BEAR_THR:
                    bear_fwd.append(fwd)
                    if fwd < -HIT_RS: hits += 1
                    elif fwd > HIT_RS: misses += 1
                    else: pushes += 1
            if len(day_rows) >= 6:  # enough sectors to rank top/bottom 3
                day_rows.sort(key=lambda x: x[1], reverse=True)
                top3 = sum(r[2] for r in day_rows[:3]) / 3
                bot3 = sum(r[2] for r in day_rows[-3:]) / 3
                spreads.append(top3 - bot3)
                scored_days += 1

        graded = hits + misses
        results[f"{n}d"] = {
            "horizon_sessions": n,
            "directional_hit_rate": round(hits / graded * 100, 1) if graded else None,
            "hits": hits, "misses": misses, "pushes": pushes,
            "avg_fwd_rs_bullish": round(sum(bull_fwd) / len(bull_fwd), 2) if bull_fwd else None,
            "avg_fwd_rs_bearish": round(sum(bear_fwd) / len(bear_fwd), 2) if bear_fwd else None,
            "edge_top3_minus_bottom3": round(sum(spreads) / len(spreads), 2) if spreads else None,
            "scored_days": scored_days,
        }
    return results


def build() -> tuple[str, dict]:
    res = evaluate()
    hist = json.loads(HISTORY.read_text()).get("series", [])
    n_real = sum(1 for e in hist if "(backfill" not in (e.get("regime_summary") or ""))
    today = date.today().isoformat()

    lines = [
        f"# Rotation Engine Scorecard — {today}",
        "",
        f"Backtest tự kiểm của engine: điểm `rotation_score` tại ngày D có dự báo đúng "
        f"forward RS (vs SPY) {HORIZONS[0]}–{HORIZONS[-1]} phiên sau không? "
        f"Cửa sổ history: **{len(hist)} phiên** (trong đó **{n_real} phiên dữ liệu THẬT**, "
        f"còn lại backfill — độ tin tăng dần khi chạy `/daily-macro` mỗi ngày).",
        "",
        "| Horizon | Hit rate hướng | Edge (top3−bot3 fwd RS) | Bull avg fwd | Bear avg fwd | n chấm |",
        "|---|---|---|---|---|---|",
    ]
    for n in HORIZONS:
        r = res[f"{n}d"]
        hr = f"{r['directional_hit_rate']}%" if r["directional_hit_rate"] is not None else "—"
        edge = f"{r['edge_top3_minus_bottom3']:+.2f}%" if r["edge_top3_minus_bottom3"] is not None else "—"
        bull = f"{r['avg_fwd_rs_bullish']:+.2f}%" if r["avg_fwd_rs_bullish"] is not None else "—"
        bear = f"{r['avg_fwd_rs_bearish']:+.2f}%" if r["avg_fwd_rs_bearish"] is not None else "—"
        lines.append(f"| {n} phiên | {hr} | {edge} | {bull} | {bear} | {r['hits']+r['misses']} |")

    lines += [
        "",
        "> **Edge** = trung bình mỗi ngày: (forward RS của 3 sector điểm cao nhất) − (3 sector thấp nhất). "
        "Dương = thứ hạng engine có giá trị. **Hit rate** = trong các call có hướng rõ "
        f"(|score|>{BULL_THR}), tỷ lệ forward RS đúng hướng (ngưỡng ±{HIT_RS}%).",
        "> ⚠️ Mẫu còn nhỏ + phần lớn backfill → đọc như tín hiệu sơ bộ, không phải kết luận. "
        "Chạy daily đều để mẫu lớn dần.",
        "",
        "---",
        "",
    ]
    md = "\n".join(lines)
    js = {"generated_at": datetime.now(timezone.utc).isoformat(),
          "history_sessions": len(hist), "real_sessions": n_real,
          "params": {"BULL_THR": BULL_THR, "BEAR_THR": BEAR_THR, "HIT_RS": HIT_RS},
          "results": res}
    return md, js


def main() -> int:
    if not HISTORY.exists():
        print("Chưa có sector_rotation_history.json — chạy build_sector_rotation.py trước.")
        return 0
    md, js = build()
    OUT_MD.write_text(md)
    OUT_JSON.write_text(json.dumps(js, indent=2, ensure_ascii=False))
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_JSON}")
    for n in HORIZONS:
        r = js["results"][f"{n}d"]
        print(f"  {n}d: hit {r['directional_hit_rate']}% | edge {r['edge_top3_minus_bottom3']}% "
              f"| bull {r['avg_fwd_rs_bullish']} vs bear {r['avg_fwd_rs_bearish']} (n={r['hits']+r['misses']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
