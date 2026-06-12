#!/usr/bin/env python3
"""Replace stubs in category 'Cần Bổ Sung' with proper educational content."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THEORY = ROOT / "data" / "macro_theory.json"

# Stub replacements: indicator_id_in_stub → (target_category, full_entry)
# Stub IDs were generated as uppercase underscored version of normalized name.
REPLACEMENTS = [
    # EIA refinery sub-components — assign to energy
    ("energy", {
        "id": "EIA_REFINERY_RUNS",
        "short_name": "EIA Refinery Runs",
        "full_name": "EIA Weekly Refinery Crude Runs",
        "frequency": "Hàng tuần (Thứ Tư)",
        "link": "https://www.eia.gov/petroleum/weekly/",
        "description": "Sản lượng dầu thô được refineries chạy qua mỗi tuần (mb/d).",
        "expectation_meaning": "Tăng = refineries chạy hết công suất → demand cho sản phẩm xăng/diesel mạnh. Giảm = maintenance season hoặc demand cool.",
        "good_vs_bad": "Mạnh = supportive cho XLE (refiners: VLO, MPC, PSX). Weak = refining margins (crack spread) co.",
        "market_reaction": "Niche. Combined với Refinery Utilization để gauge sức khoẻ refining sector.",
        "release_aliases": ["eia refinery crude runs"],
    }),
    ("energy", {
        "id": "EIA_DISTILLATES_STOCKS",
        "short_name": "Distillates Stocks",
        "full_name": "EIA Weekly Distillates Stocks (Diesel + Heating Oil)",
        "frequency": "Hàng tuần (Thứ Tư)",
        "link": "https://www.eia.gov/petroleum/weekly/",
        "description": "Tồn kho diesel + heating oil. Phản ánh demand transport (diesel) và mùa đông (heating).",
        "expectation_meaning": "Builds vào mùa hè + draws vào đông. Surprise vs season = price signal.",
        "good_vs_bad": "Low stocks + mùa đông sắp tới = diesel/heating oil price spike.",
        "market_reaction": "Ảnh hưởng cracking spreads → refiners (VLO, MPC) react.",
        "release_aliases": ["eia weekly distillates stocks", "distillate fuel production", "heating oil stockpiles"],
    }),
    ("energy", {
        "id": "EIA_GASOLINE_PROD",
        "short_name": "Gasoline Production",
        "full_name": "EIA Weekly Gasoline Production",
        "frequency": "Hàng tuần (Thứ Tư)",
        "link": "https://www.eia.gov/petroleum/weekly/",
        "description": "Sản lượng xăng tuần từ refineries Mỹ.",
        "expectation_meaning": "Cao mùa hè (driving season). Drop = refinery issues.",
        "good_vs_bad": "Combined với Gasoline Inventories → gauge xăng supply/demand.",
        "market_reaction": "Niche. Energy traders dùng.",
        "release_aliases": ["gasoline production"],
    }),
    ("energy", {
        "id": "EIA_GASOLINE_INV",
        "short_name": "Gasoline Inventories",
        "full_name": "EIA Weekly Gasoline Inventories",
        "frequency": "Hàng tuần (Thứ Tư)",
        "link": "https://www.eia.gov/petroleum/weekly/",
        "description": "Tồn kho xăng thương mại tuần.",
        "expectation_meaning": "Draws đặc biệt mùa hè (driving season) = bullish gasoline + WTI. Builds = bearish.",
        "good_vs_bad": "Big draw + mùa hè = retail gasoline prices up → headline CPI Energy spike.",
        "market_reaction": "WTI react. CPI Energy component reflects retail gasoline 2-4 tuần sau.",
        "release_aliases": ["gasoline inventories"],
    }),
    ("energy", {
        "id": "EIA_REFINERY_UTIL",
        "short_name": "Refinery Utilization",
        "full_name": "EIA Weekly Refinery Utilization Rates",
        "frequency": "Hàng tuần (Thứ Tư)",
        "link": "https://www.eia.gov/petroleum/weekly/",
        "description": "% công suất refineries Mỹ đang chạy.",
        "expectation_meaning": "Bình thường 88-95%. < 85% = maintenance hoặc demand yếu. > 95% = max capacity (rare).",
        "good_vs_bad": "Cao + crack spread tốt = refiners ăn nên làm. Thấp = margin pressure.",
        "market_reaction": "VLO, MPC, PSX react. Indirect WTI impact (refineries demand crude).",
        "release_aliases": ["eia weekly refinery utilization rates"],
    }),
    ("energy", {
        "id": "EIA_STEO",
        "short_name": "EIA STEO",
        "full_name": "EIA Short-Term Energy Outlook",
        "frequency": "Hàng tháng",
        "link": "https://www.eia.gov/outlooks/steo/",
        "description": "Báo cáo dự báo cung-cầu năng lượng Mỹ + global 12-24 tháng tới.",
        "expectation_meaning": "EIA revise WTI/Brent/natural gas forecasts. Bullish/bearish revisions move XLE.",
        "good_vs_bad": "EIA forecast tighter oil market (lower inventories) = bullish XLE.",
        "market_reaction": "Big monthly mover for energy thesis. Combined với OPEC Monthly + IEA Monthly để xây global oil view.",
        "release_aliases": ["eia short-term energy outlook"],
    }),
    # Corporate Profits → growth
    ("growth", {
        "id": "CORPPROFITS",
        "short_name": "Corporate Profits",
        "full_name": "Corporate Profits (QoQ)",
        "frequency": "Hàng quý (kèm GDP revision)",
        "link": "https://www.bea.gov/data/income-saving/corporate-profits",
        "description": "Lợi nhuận sau thuế của doanh nghiệp Mỹ. Là bottom-line cho S&P 500 EPS.",
        "expectation_meaning": "Profit margins giảm = cảnh báo EPS forward S&P 500. Margin expansion = bull thesis.",
        "good_vs_bad": "Profit margins ổn định high (~12%) = bull market sustainable. Drop = earnings cycle xấu.",
        "market_reaction": "Major macro driver cho equity valuations. Trend > level quan trọng.",
        "release_aliases": ["corporate profits"],
    }),
    # ISM Non-Mfg Business Activity → growth (sub-component of ISM Services)
    ("growth", {
        "id": "ISMSVCBA",
        "short_name": "ISM Svc Activity",
        "full_name": "ISM Non-Manufacturing Business Activity Index",
        "frequency": "Hàng tháng",
        "link": "https://www.ismworld.org/",
        "description": "Sub-component ISM Services PMI — đo hoạt động kinh doanh services 'right now'.",
        "expectation_meaning": "> 55 = services khoẻ. < 50 hiếm gặp = services contraction.",
        "good_vs_bad": "Services chiếm ~80% GDP. Component này yếu = headline ISM Svc PMI cũng yếu.",
        "market_reaction": "Track cùng ISM Svc PMI headline. Spread giữa Business Activity vs New Orders cho insight về momentum.",
        "release_aliases": ["ism non-manufacturing business activity"],
    }),
    # Thomson Reuters IPSOS PCSI → confidence
    ("confidence", {
        "id": "IPSOSPCSI",
        "short_name": "IPSOS PCSI",
        "full_name": "Thomson Reuters IPSOS Primary Consumer Sentiment Index",
        "frequency": "Hàng tháng",
        "link": "https://www.ipsos.com/en/economy/PCSI",
        "description": "Khảo sát consumer sentiment global do IPSOS thực hiện cho Reuters. Đo perception về kinh tế cá nhân + quốc gia.",
        "expectation_meaning": "Less Fed-watched than Michigan/CB. Cross-check international consumer mood.",
        "good_vs_bad": "Niche. Useful when Michigan/CB divergent.",
        "market_reaction": "Minor mover. Pros dùng để diversify consumer reads.",
        "release_aliases": ["thomson reuters ipsos pcsi"],
    }),
]


def main() -> int:
    if not THEORY.exists():
        print(f"Theory missing: {THEORY}", file=sys.stderr)
        return 1

    theory = json.loads(THEORY.read_text())

    # Remove the "Cần Bổ Sung" placeholder category entirely — its stubs will be replaced with real content
    cats_before = len(theory["categories"])
    theory["categories"] = [c for c in theory["categories"] if c.get("id") != "pending"]
    if len(theory["categories"]) < cats_before:
        print("Removed placeholder category 'Cần Bổ Sung' — replacing stubs with quality content")

    cat_map = {c["id"]: c for c in theory["categories"]}

    added = 0
    skipped = 0
    for cat_id, ind in REPLACEMENTS:
        cat = cat_map.get(cat_id)
        if not cat:
            print(f"  category {cat_id} missing")
            continue
        existing_ids = {i["id"] for i in cat["indicators"]}
        if ind["id"] in existing_ids:
            skipped += 1
            continue
        cat["indicators"].append(ind)
        added += 1

    THEORY.write_text(json.dumps(theory, indent=2, ensure_ascii=False))
    total = sum(len(c["indicators"]) for c in theory["categories"])
    print(f"Added {added} supplemented indicators ({skipped} existed).")
    print(f"Total: {total} across {len(theory['categories'])} categories.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
