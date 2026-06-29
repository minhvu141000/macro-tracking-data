#!/usr/bin/env python3
"""Tầng ĐỐI CHIẾU view quỹ — đồng thuận tổ chức (institutional consensus cross-check).

Đọc data/fund_views_latest.json (view sector thô từ các quỹ lớn, do bước nghiên cứu
web cập nhật mỗi quý) và tổng hợp TẤT ĐỊNH thành điểm đồng thuận per-sector, rồi đối
chiếu với verdict của rotation engine (data/sector_rotation_confirmed.json).

Triết lý: KHÔNG trộn view quỹ vào điểm rotation engine (giữ engine tất định & chấm
điểm được). Đây là tầng độc lập trả lời: "Các quỹ lớn đang nghiêng về ngành nào, và
nó KHỚP hay LỆCH với tín hiệu macro→dòng tiền tất định của ta?"

Consensus per sector:
  • net_score   = trung bình các tilt khác null trên các quỹ (∈ [-1, 1])
  • n_funds     = số quỹ có nêu view (không null)
  • bull/bear   = số quỹ OW / UW
  • label       = STRONG_OW / OW / MIXED / N / UW / STRONG_UW theo net_score & đồng thuận

Cross-check vs verdict tất định:
  • AGREE       — quỹ và engine cùng hướng (cùng thiên về vào / tránh)
  • DIVERGE     — ngược hướng (cờ để soi kỹ)
  • PARTIAL/NA  — một bên trung tính hoặc thiếu dữ liệu

Cũng phát hiện báo cáo CŨ (stale): cảnh báo nếu report quá ngưỡng ngày tuổi.

Output:
  data/fund_consensus_latest.json  — đồng thuận + cross-check (cho dashboard/agent)
  data/fund_views_report.md        — báo cáo đọc nhanh tiếng Việt

    python scripts/build_fund_consensus.py
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_sector_rotation import SECTOR_NAMES

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "fund_views_latest.json"
# Neo đối chiếu = DỰ BÁO rotation tháng/quý tới (forward), khớp ý "nhóm nào nhận
# tiền quý tới". Fallback sang verdict tuần nếu chưa có forecast.
FORECAST = DATA / "monthly_rotation_forecast_latest.json"
CONFIRMED = DATA / "sector_rotation_confirmed.json"
OUT_JSON = DATA / "fund_consensus_latest.json"
OUT_MD = DATA / "fund_views_report.md"

STALE_DAYS = 100  # báo cáo quý cũ hơn ~3.3 tháng coi là stale

# Phase dự báo forward nào coi là "sẽ nhận tiền" / "sẽ mất tiền"
BULLISH_PHASES = {"INFLOW_LIKELY", "FORMING", "CONFIRMED_IN", "EARLY_FORMING"}
BEARISH_PHASES = {"OUTFLOW_LIKELY", "AVOID", "FADING"}


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def consensus_label(net: float, n_bull: int, n_bear: int) -> str:
    if net >= 0.66:
        return "STRONG_OW"
    if net >= 0.25:
        return "OW"
    if net <= -0.66:
        return "STRONG_UW"
    if net <= -0.25:
        return "UW"
    if n_bull and n_bear:
        return "MIXED"
    return "N"


def crosscheck(cons_net: float, phase: str | None) -> str:
    if phase is None:
        return "NA"
    cons_dir = 1 if cons_net >= 0.25 else (-1 if cons_net <= -0.25 else 0)
    eng_dir = 1 if phase in BULLISH_PHASES else (-1 if phase in BEARISH_PHASES else 0)
    if cons_dir == 0 or eng_dir == 0:
        return "PARTIAL"
    return "AGREE" if cons_dir == eng_dir else "DIVERGE"


def main() -> int:
    if not RAW.exists():
        print(f"ERROR: không thấy {RAW}", file=sys.stderr)
        return 1
    raw = json.loads(RAW.read_text())
    sources = raw.get("sources", [])
    today = _today()

    # cảnh báo stale
    stale = []
    for s in sources:
        d = _parse_date(s.get("as_of", ""))
        age = (today - d).days if d else None
        s["_age_days"] = age
        if age is not None and age > STALE_DAYS:
            stale.append(f"{s['fund']} ({s['as_of']}, {age}d)")

    # neo engine: ưu tiên DỰ BÁO forward (tháng tới), fallback verdict tuần
    phases = {}
    fc_meta = {}  # ticker -> {phase, score, confidence} từ dự báo tháng (cho luận điểm)
    regime = None
    engine_anchor = None
    target_month = None
    if FORECAST.exists():
        fc = json.loads(FORECAST.read_text())
        regime = fc.get("regime_summary")
        target_month = fc.get("target_month")
        engine_anchor = {"type": "monthly_forecast", "target_month": target_month,
                         "as_of": fc.get("as_of")}
        for it in fc.get("items", []):
            phases[it["ticker"]] = it.get("phase")
            fc_meta[it["ticker"]] = {"phase": it.get("phase"),
                                     "score": it.get("forecast_score"),
                                     "confidence": it.get("confidence")}
    elif CONFIRMED.exists():
        conf = json.loads(CONFIRMED.read_text())
        regime = conf.get("regime_summary")
        engine_anchor = {"type": "weekly_confirmed", "as_of": conf.get("as_of_latest")}
        for tk, info in conf.get("sectors", {}).items():
            phases[tk] = info.get("confirmed_phase")

    # tổng hợp per sector
    sectors = {}
    for tk, name in SECTOR_NAMES.items():
        tilts, bull, bear, per_fund = [], 0, 0, []
        for s in sources:
            v = s.get("views", {}).get(tk)
            if not v or v.get("tilt") is None:
                continue
            t = v["tilt"]
            tilts.append(t)
            bull += 1 if t > 0 else 0
            bear += 1 if t < 0 else 0
            per_fund.append({
                "fund": s["fund"], "tilt": t,
                "label": v.get("label"), "note": v.get("note"),
                "lens": s.get("lens", "flow"),
                "verified": s.get("verified", False),
            })
        n = len(tilts)
        net = round(sum(tilts) / n, 3) if n else 0.0
        label = consensus_label(net, bull, bear) if n else "NA"
        phase = phases.get(tk)
        sectors[tk] = {
            "name": name,
            "consensus_label": label,
            "net_score": net,
            "n_funds": n,
            "n_overweight": bull,
            "n_underweight": bear,
            "engine_phase": phase,
            "crosscheck": crosscheck(net, phase) if n else "NA",
            "fund_views": per_fund,
        }

    ranked = sorted(sectors, key=lambda t: (-sectors[t]["net_score"], -sectors[t]["n_funds"]))
    diverge = [t for t in ranked if sectors[t]["crosscheck"] == "DIVERGE"]

    out = {
        "schema_version": "1.0",
        "tier": "fund-consensus",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_today": today.isoformat(),
        "n_sources": len(sources),
        "sources_meta": [
            {"fund": s["fund"], "report": s.get("report"), "as_of": s.get("as_of"),
             "age_days": s["_age_days"], "verified": s.get("verified", False),
             "coverage": s.get("coverage"), "url": s.get("url")}
            for s in sources
        ],
        "stale_warning": stale,
        "engine_anchor": engine_anchor,
        "engine_regime": regime,
        "ranked": ranked,
        "divergences": diverge,
        "sectors": sectors,
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    write_markdown(out)
    thesis_path = write_thesis(out, fc_meta, target_month)
    print(f"OK: {OUT_JSON.relative_to(ROOT)} + {OUT_MD.relative_to(ROOT)}")
    if thesis_path:
        print(f"OK thesis: {thesis_path.relative_to(ROOT)}")
    if stale:
        print("⚠ STALE reports:", "; ".join(stale))
    if diverge:
        print("⚠ DIVERGE (quỹ ≠ engine):", ", ".join(diverge))
    return 0


CC_VI = {"AGREE": "✅ KHỚP", "DIVERGE": "⚠️ LỆCH", "PARTIAL": "◐ một phần",
         "NA": "—"}
LBL_VI = {"STRONG_OW": "Mạnh OW", "OW": "OW", "MIXED": "Trái chiều",
          "N": "Trung tính", "UW": "UW", "STRONG_UW": "Mạnh UW", "NA": "Không có"}


def write_markdown(out: dict) -> None:
    L = []
    L.append("# Đồng thuận phân bổ ngành — các quỹ lớn Mỹ\n")
    L.append(f"_Tổng hợp: {out['as_of_today']} · {out['n_sources']} nguồn · tầng đối chiếu (KHÔNG trộn vào rotation engine)_\n")
    ea = out.get("engine_anchor") or {}
    if ea.get("type") == "monthly_forecast":
        L.append(f"> **Neo đối chiếu:** DỰ BÁO rotation tháng tới `{ea.get('target_month')}` (forward, từ build_monthly_rotation.py) — khớp câu hỏi 'nhóm nào nhận tiền quý tới'.\n")
    elif ea.get("type") == "weekly_confirmed":
        L.append(f"> **Neo đối chiếu:** verdict tuần (chưa có dự báo tháng) as_of `{ea.get('as_of')}`.\n")
    if out.get("engine_regime"):
        L.append(f"> **Regime engine:** {out['engine_regime']}\n")
    if out.get("stale_warning"):
        L.append(f"> ⚠️ **Báo cáo cũ (>{STALE_DAYS}d):** {'; '.join(out['stale_warning'])} — cần làm mới.\n")

    L.append("## Nguồn\n")
    L.append("| Quỹ | Báo cáo | Ngày | Tuổi | Verify | Phủ |")
    L.append("|---|---|---|---|---|---|")
    for s in out["sources_meta"]:
        v = "✓" if s["verified"] else "✗ (suy luận)"
        age = f"{s['age_days']}d" if s["age_days"] is not None else "?"
        L.append(f"| {s['fund']} | {s['report']} | {s['as_of']} | {age} | {v} | {s['coverage']} |")
    L.append("")

    L.append("## Bảng đồng thuận (xếp theo net score)\n")
    L.append("| Ngành | Đồng thuận | Net | #OW | #UW | Dự báo engine | Đối chiếu |")
    L.append("|---|---|---:|---:|---:|---|---|")
    for tk in out["ranked"]:
        s = out["sectors"][tk]
        if s["n_funds"] == 0:
            continue
        L.append(f"| {tk} {s['name']} | {LBL_VI.get(s['consensus_label'])} | "
                 f"{s['net_score']:+.2f} | {s['n_overweight']} | {s['n_underweight']} | "
                 f"{s['engine_phase'] or '—'} | {CC_VI.get(s['crosscheck'])} |")
    L.append("")

    if out.get("divergences"):
        L.append("## ⚠️ Điểm LỆCH (quỹ ≠ dự báo engine) — soi kỹ\n")
        for tk in out["divergences"]:
            s = out["sectors"][tk]
            lenses = {fv.get("lens", "flow") for fv in s["fund_views"]}
            tag = " _(gồm lăng kính định giá Morningstar — lệch momentum là tension bình thường)_" if "value" in lenses else ""
            L.append(f"- **{tk} {s['name']}**: quỹ {LBL_VI.get(s['consensus_label'])} "
                     f"(net {s['net_score']:+.2f}) nhưng dự báo engine `{s['engine_phase']}`.{tag}")
        L.append("")

    L.append("## Chi tiết view từng quỹ\n")
    for tk in out["ranked"]:
        s = out["sectors"][tk]
        if s["n_funds"] == 0:
            continue
        L.append(f"### {tk} — {s['name']}  ·  {LBL_VI.get(s['consensus_label'])} (net {s['net_score']:+.2f})")
        for fv in s["fund_views"]:
            arrow = "▲" if fv["tilt"] > 0 else ("▼" if fv["tilt"] < 0 else "■")
            note = f" — {fv['note']}" if fv.get("note") else ""
            lens = " _[định giá]_" if fv.get("lens") == "value" else ""
            L.append(f"- {arrow} **{fv['fund']}**{lens} ({fv.get('label') or '?'}){note}")
        L.append("")

    L.append("---")
    L.append("_Nguồn dữ liệu thô: `data/fund_views_latest.json`. Cập nhật mỗi quý qua nghiên cứu web rồi chạy `python scripts/build_fund_consensus.py`._")
    OUT_MD.write_text("\n".join(L))


# Phase engine coi là "dự báo TĂNG TRƯỞNG / nhận dòng tiền"
GROWTH_PHASES = {"INFLOW_LIKELY", "FORMING", "CONFIRMED_IN", "EARLY_FORMING"}


def write_thesis(out: dict, fc_meta: dict, target_month: str | None) -> Path | None:
    """Section LUẬN ĐIỂM ĐẦU TƯ cho các nhóm ngành engine DỰ BÁO TĂNG TRƯỞNG —
    trích lý lẽ forward từ các quỹ. Báo cáo tháng COPY nguyên section này vào.

    Tất định: ngành = giao của (engine forecast growth) ∪ (quỹ đồng thuận OW),
    ưu tiên ngành engine dự báo tăng. Mỗi ngành liệt kê luận điểm bull từ từng quỹ
    + cờ rủi ro nếu có quỹ bearish hoặc engine không xác nhận.
    """
    if not target_month:
        return None
    sectors = out["sectors"]
    # ngành engine dự báo tăng trưởng (sắp theo net đồng thuận quỹ)
    growth = [tk for tk in out["ranked"]
              if sectors[tk]["engine_phase"] in GROWTH_PHASES]

    L = []
    L.append(f"## Luận điểm đầu tư nhóm ngành — dự báo tăng trưởng {target_month} (từ các quỹ)\n")
    L.append(f"_Nguồn: J.P. Morgan · Goldman Sachs · State Street SPDR · Morningstar. "
             f"Đối chiếu với dự báo rotation engine tháng `{target_month}`. "
             f"Tầng cross-check — KHÔNG trộn vào điểm engine._\n")
    if out.get("stale_warning"):
        L.append(f"> ⚠️ Báo cáo cũ cần làm mới: {'; '.join(out['stale_warning'])}.\n")

    if not growth:
        L.append("_Engine không dự báo ngành nào ở pha tăng trưởng kỳ này._")
    for tk in growth:
        s = sectors[tk]
        m = fc_meta.get(tk, {})
        sc = m.get("score")
        sc_txt = f", score {sc:+.2f}" if isinstance(sc, (int, float)) else ""
        L.append(f"### {tk} — {s['name']}")
        L.append(f"- **Engine dự báo:** `{m.get('phase', s['engine_phase'])}` "
                 f"(confidence {m.get('confidence', '?')}{sc_txt}). "
                 f"Đồng thuận quỹ: **{LBL_VI.get(s['consensus_label'])}** "
                 f"(net {s['net_score']:+.2f}, {s['n_overweight']} OW / {s['n_underweight']} UW) "
                 f"→ {CC_VI.get(s['crosscheck'])}.")
        bulls = [fv for fv in s["fund_views"] if fv["tilt"] > 0]
        bears = [fv for fv in s["fund_views"] if fv["tilt"] < 0]
        if bulls:
            L.append("- **Luận điểm tăng trưởng (bull):**")
            for fv in bulls:
                lens = " _[định giá]_" if fv.get("lens") == "value" else ""
                note = fv.get("note") or fv.get("label") or ""
                L.append(f"  - {fv['fund']}{lens}: {note}")
        if bears:
            L.append("- **⚠️ Rủi ro / phản biện (bear):**")
            for fv in bears:
                lens = " _[định giá]_" if fv.get("lens") == "value" else ""
                note = fv.get("note") or fv.get("label") or ""
                L.append(f"  - {fv['fund']}{lens}: {note}")
        if s["crosscheck"] == "AGREE":
            L.append("- **Chốt:** Quỹ và dự báo macro→flow CÙNG hướng tăng → độ tin cậy cao.")
        elif s["crosscheck"] == "DIVERGE":
            L.append("- **Chốt:** Engine dự báo tăng nhưng quỹ thận trọng/ngược → soi kỹ trước khi nâng tỷ trọng.")
        else:
            L.append("- **Chốt:** Tín hiệu một phần — quỹ hoặc engine chưa dứt khoát.")
        L.append("")

    # ngành quỹ bullish nhưng engine KHÔNG dự báo tăng (cơ hội quỹ thấy sớm hơn)
    fund_only = [tk for tk in out["ranked"]
                 if sectors[tk]["consensus_label"] in ("STRONG_OW", "OW")
                 and sectors[tk]["engine_phase"] not in GROWTH_PHASES]
    if fund_only:
        L.append("### Quỹ bullish nhưng engine CHƯA dự báo tăng (theo dõi sớm)")
        for tk in fund_only:
            s = sectors[tk]
            L.append(f"- **{tk} {s['name']}**: quỹ {LBL_VI.get(s['consensus_label'])} "
                     f"(net {s['net_score']:+.2f}) vs engine `{s['engine_phase']}` — "
                     f"theme dài hạn quỹ thấy trước khi dòng tiền ngắn hạn xác nhận.")
        L.append("")

    L.append("_Sinh tất định bởi `scripts/build_fund_consensus.py` từ `data/fund_views_latest.json` + `data/monthly_rotation_forecast_latest.json`._")

    out_path = DATA / "monthly" / f"fund_thesis_{target_month}.md"
    out_path.write_text("\n".join(L))
    return out_path


if __name__ == "__main__":
    raise SystemExit(main())
