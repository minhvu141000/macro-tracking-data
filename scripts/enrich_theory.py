#!/usr/bin/env python3
"""Enrich each indicator in macro_theory.json with 4 critical learning fields:
- read_format: how to read it (MoM/YoY/level/etc with primary view)
- watch_thresholds: explicit threshold numbers (e.g. "VIX <15 complacency, >25 stress")
- release_pattern: precise schedule ("First Friday 8:30 ET")
- related_indicators: list of FRED IDs to cross-reference

Also adds new top-level category "Khái Niệm Cơ Bản" with ~15 glossary entries
that teach foundational vocab (SA/NSA, surprise/sigma, headline vs core, etc).

Run once; idempotent (skips if fields already exist).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THEORY = ROOT / "data" / "macro_theory.json"

# ============================================================================
# Per-indicator enrichment. Map indicator ID → fields to add.
# Indicators not in this map get auto-default based on category (below).
# ============================================================================

ENRICHMENTS = {
    # ====== INFLATION ======
    "CPIAUCSL": {
        "read_format": "**YoY%** (primary, Fed target 2%) · **MoM%** (momentum, > 0.3% nóng) · **3-mo annualized** (Fed view ngắn hạn)",
        "watch_thresholds": "YoY <2% = anchored / 2-3% = neutral / 3-4% = sticky → Fed lo / >4% = problem",
        "release_pattern": "Hàng tháng, khoảng ngày 10-15 của tháng sau, 8:30 ET (BLS)",
        "related_indicators": ["CPILFESL", "PCEPI", "PCEPILFE", "PPIFID", "MICH1Y"],
    },
    "CPILFESL": {
        "read_format": "**YoY%** (primary, Fed lo nhất) · **3-mo annualized** (sticky inflation gauge) · MoM% (noise nhiều)",
        "watch_thresholds": "YoY <2.5% = good / 2.5-3.5% = sticky / >3.5% = Fed buộc hawkish",
        "release_pattern": "Cùng CPI headline, 8:30 ET",
        "related_indicators": ["CPIAUCSL", "PCEPILFE", "MEDCPIM158SFRBCLE"],
    },
    "PCEPI": {
        "read_format": "**YoY%** · **MoM%** — Fed's chosen target (vs CPI), 2% là target chính thức",
        "watch_thresholds": "YoY = Fed target 2.0% chính thức. <2% disinflation / 2-2.5% on-track / >3% sticky",
        "release_pattern": "Cuối tháng, ~25-30, 8:30 ET (BEA)",
        "related_indicators": ["PCEPILFE", "CPIAUCSL", "PI", "PCE"],
    },
    "PCEPILFE": {
        "read_format": "**YoY%** (Fed's #1 metric) · **3-mo annualized** (favored by Powell) · MoM% (noise)",
        "watch_thresholds": "YoY: <2.5% = Fed có thể cut / 2.5-3% = pause / >3% = no cuts. 3-mo > 4% = hawkish urgency.",
        "release_pattern": "Cuối tháng, ~25-30, 8:30 ET. **Sau CPI 2 tuần** → market đã price phần lớn.",
        "related_indicators": ["CPILFESL", "PCEPI", "ULCNFB", "AHE"],
    },
    "PPIFID": {
        "read_format": "**YoY%** (pipeline pressure) · **MoM%** (recent shock) · 3-mo annualized (truyền dẫn vào CPI)",
        "watch_thresholds": "YoY <3% = clean / 5-8% = warning / >10% = sẽ truyền vào CPI 2-3 tháng",
        "release_pattern": "Hàng tháng, ~ngày 11-15 (1 ngày trước CPI), 8:30 ET",
        "related_indicators": ["PPILFE", "CPIAUCSL", "ISMMFGPRICES"],
    },
    "PPILFE": {
        "read_format": "**YoY%** + **MoM%** — sticky pipeline; Fed dùng cross-check Core CPI/PCE",
        "watch_thresholds": "YoY <2.5% = anchored / >3.5% = sticky pipeline",
        "release_pattern": "Cùng PPI headline",
        "related_indicators": ["PPIFID", "CPILFESL"],
    },
    "MEDCPIM158SFRBCLE": {
        "read_format": "**YoY%** chính · MoM% noisy. Median = strip outliers tốt hơn Core CPI",
        "watch_thresholds": "YoY <3% = anchored / >4% = sticky / >5% = unanchored (lần cuối 2022)",
        "release_pattern": "Cùng CPI, vài giờ sau",
        "related_indicators": ["CPILFESL", "CPIAUCSL"],
    },

    # ====== LABOR ======
    "PAYEMS": {
        "read_format": "**Δ MoM (Net jobs added, K)** primary — KHÔNG xem level. YoY% = trend dài hạn",
        "watch_thresholds": "<+100K weak / 100-150K cooling / 150-200K healthy / >200K hot. <0 = recession",
        "release_pattern": "**First Friday** của tháng sau, 8:30 ET. Lớn nhất tháng.",
        "related_indicators": ["UNRATE", "AHE", "ICSA", "JTSJOL", "ADPMNUSNERNSA"],
    },
    "UNRATE": {
        "read_format": "**Level** (đã là %, không transform). Theo dõi **3-month MA** để smooth + Sahm rule",
        "watch_thresholds": "<4% = tight / 4-5% = normal / >5% = cooling / Sahm trigger: 3M MA cao hơn 0.5pp so 12M low",
        "release_pattern": "Cùng NFP, First Friday 8:30 ET",
        "related_indicators": ["PAYEMS", "U6RATE", "CIVPART", "ICSA"],
    },
    "ICSA": {
        "read_format": "**Level (K, weekly)** primary · **4-week MA** giảm nhiễu · KHÔNG xem YoY",
        "watch_thresholds": "<220K = strong / 220-250K = normal / >280K = warning / >320K = recession-like",
        "release_pattern": "**Mọi Thứ Năm 8:30 ET**, data tuần kết thúc Thứ Bảy trước",
        "related_indicators": ["CCSA", "IC4WSA", "CHALLENGER", "PAYEMS"],
    },
    "CES0500000003": {
        "read_format": "**YoY%** primary (wage growth) · MoM% momentum · KHÔNG xem level USD",
        "watch_thresholds": "YoY <3% = labor cool / 3-4% = healthy / >4.5% = wage-price spiral risk",
        "release_pattern": "Cùng NFP, First Friday",
        "related_indicators": ["PAYEMS", "ULCNFB", "PCEPILFE"],
    },
    "JTSJOL": {
        "read_format": "**Level (M openings)** + **ratio openings/unemployed** quan trọng hơn",
        "watch_thresholds": "Ratio >1.5x = labor cực chặt / 1.0-1.3x = balanced / <1.0x = lỏng",
        "release_pattern": "Khoảng ngày 5-7 của 2 tháng sau (lag 1 tháng), 10:00 ET",
        "related_indicators": ["UNRATE", "PAYEMS", "CHALLENGER"],
    },
    "CCSA": {
        "read_format": "**Level (M, weekly)** + **trend (4-week MA)**. KHÔNG xem YoY/MoM",
        "watch_thresholds": "<1.5M = strong / 1.5-1.8M = normal / >2.0M = labor stress",
        "release_pattern": "Cùng Initial Claims, Thứ Năm 8:30 ET",
        "related_indicators": ["ICSA", "IC4WSA", "PAYEMS"],
    },
    "ADPMNUSNERNSA": {
        "read_format": "**Δ MoM (K)** — preview cho NFP. Correlate ~0.6 với NFP",
        "watch_thresholds": "<100K = weak / 100-180K = healthy / >200K = hot. Diff với NFP thường ±50K",
        "release_pattern": "Thứ Tư đầu tiên (2 ngày trước NFP), 8:15 ET",
        "related_indicators": ["PAYEMS", "ICSA"],
    },
    "CHALLENGER": {
        "read_format": "**Level (K announcements)** + **YoY%** (so cùng tháng năm trước)",
        "watch_thresholds": "<50K = bình thường / 80-100K = layoff cycle bắt đầu / >150K = stress",
        "release_pattern": "Thứ Năm đầu tháng, 7:30 ET",
        "related_indicators": ["ICSA", "PAYEMS"],
    },
    "OPHNFB": {
        "read_format": "**YoY%** trend dài hạn · **QoQ annualized** quarterly read",
        "watch_thresholds": "<1% = stagflation risk / 1-2% = normal / >3% = boom (AI?)",
        "release_pattern": "Đầu tháng (5-9 ngày làm việc), 8:30 ET, quarterly",
        "related_indicators": ["ULCNFB", "GDPC1"],
    },

    # ====== GROWTH ======
    "GDPC1": {
        "read_format": "**QoQ annualized %** (BEA official) primary · YoY% = trend",
        "watch_thresholds": "<1% weak / 1-2% slow / 2-3% trend / >3% strong. 2 quý âm liên tiếp = recession",
        "release_pattern": "3 lần/quarter: Advance (~ngày 27 tháng sau quarter end), 2nd (~30 ngày sau), Final (~60 ngày sau)",
        "related_indicators": ["GDPNOW", "PCE", "INDPRO", "RSAFS"],
    },
    "RSAFS": {
        "read_format": "**MoM%** primary · **Control group ex-auto/gas/building/food** (vào GDP) quan trọng nhất · YoY% nominal",
        "watch_thresholds": "MoM ±0.5% = noise / >+0.7% = strong / <-0.5% = consumer rút",
        "release_pattern": "Giữa tháng (~15-17) sau tháng tham chiếu, 8:30 ET",
        "related_indicators": ["PCE", "PI", "UMCSENT", "TOTALSA"],
    },
    "INDPRO": {
        "read_format": "**MoM%** primary · YoY% trend",
        "watch_thresholds": "MoM ±0.2% noise / >+0.5% boom / <-0.3% manuf weak",
        "release_pattern": "Giữa tháng (~17), 9:15 ET",
        "related_indicators": ["MANEMP", "NEWORDER", "DGORDER", "ISMMFGNEW"],
    },
    "GDPNOW": {
        "read_format": "**Level (% annualized for current Q)** · update sau mỗi data release · revision range = signal",
        "watch_thresholds": "0-1% recession risk / 1.5-2.5% trend / >3% boom. Cut >0.5pp/day = re-rate growth narrative",
        "release_pattern": "Real-time, Atlanta Fed website. Update sau ISM PMI, NFP, Retail Sales...",
        "related_indicators": ["GDPC1", "RSAFS", "INDPRO", "PCE"],
    },
    "NEWORDER": {
        "read_format": "**MoM%** primary · YoY% trend · **Ex-transport** thường stable hơn (cuts máy bay)",
        "watch_thresholds": "MoM ±1% noise / >+2% boom / <-2% manuf recession",
        "release_pattern": "Đầu tháng sau (~5), 10:00 ET",
        "related_indicators": ["DGORDER", "INDPRO", "ISMMFGNEW"],
    },
    "DGORDER": {
        "read_format": "**MoM%** primary · **Core (ex-defense, ex-aircraft)** capex proxy chính",
        "watch_thresholds": "Core MoM ±0.5% noise / >+1% capex recovery / <-1% capex cycle xấu",
        "release_pattern": "Cuối tháng (~27), 8:30 ET",
        "related_indicators": ["NEWORDER", "INDPRO", "MANEMP"],
    },
    "TTLCONS": {
        "read_format": "**MoM%** primary · YoY% trend",
        "watch_thresholds": "MoM ±0.3% noise / >+0.5% boom / <-0.5% slowing",
        "release_pattern": "Đầu tháng sau (~1-3), 10:00 ET",
        "related_indicators": ["PERMIT", "HOUST", "INDPRO"],
    },
    "PCE": {
        "read_format": "**Real MoM%** primary (đã trừ inflation) · YoY% trend",
        "watch_thresholds": "Real MoM <0 = consumer weak / 0-0.3% normal / >0.5% strong",
        "release_pattern": "Cuối tháng sau (~25-30), 8:30 ET",
        "related_indicators": ["PI", "RSAFS", "UMCSENT", "PCEPI"],
    },
    "PI": {
        "read_format": "**MoM%** primary · **Real (trừ inflation)** mới meaningful · Cross-check spending = saving rate",
        "watch_thresholds": "MoM ±0.3% noise / Income > Spending = saving rate up = consumer cẩn thận",
        "release_pattern": "Cùng PCE, 8:30 ET",
        "related_indicators": ["PCE", "AHE", "REALEARN"],
    },

    # ====== CONFIDENCE ======
    "UMCSENT": {
        "read_format": "**Level (Index)** primary · MoM% momentum",
        "watch_thresholds": ">90 = strong / 70-90 = neutral / <70 = bearish (recession-like)",
        "release_pattern": "Preliminary giữa tháng (~10-15), Final cuối tháng (~25-30), 10:00 ET",
        "related_indicators": ["CSCICP03USM665S", "MICHEXP", "MICH1Y", "MICH5Y"],
    },
    "MICH1Y": {
        "read_format": "**Level (%)** primary — Fed theo dõi sát expectations",
        "watch_thresholds": "<3% anchored / 3-4% drift up / >4% Fed lo / >5% unanchored",
        "release_pattern": "Cùng Michigan Sentiment, preliminary + final",
        "related_indicators": ["MICH5Y", "NYFED1YINFL", "T10YIE", "CPIAUCSL"],
    },
    "MICH5Y": {
        "read_format": "**Level (%)** — Fed quan trọng nhất (long-term anchored?)",
        "watch_thresholds": "<2.5% anchored / 2.5-3% normal / >3.5% Fed credibility risk",
        "release_pattern": "Cùng Michigan",
        "related_indicators": ["MICH1Y", "T10YIE"],
    },

    # ====== HOUSING ======
    "HOUST": {
        "read_format": "**Level (M annualized)** + **MoM%** · YoY% trend",
        "watch_thresholds": "<1.2M weak / 1.3-1.5M normal / >1.6M boom",
        "release_pattern": "Giữa tháng (~17-19), 8:30 ET",
        "related_indicators": ["PERMIT", "HSN1F", "MBA30Y"],
    },
    "PERMIT": {
        "read_format": "**Level (M annualized)** + **MoM%** · Leading indicator cho Housing Starts 1-3 tháng",
        "watch_thresholds": "Tương tự HOUST: <1.2M weak / >1.6M boom",
        "release_pattern": "Cùng Housing Starts",
        "related_indicators": ["HOUST", "HSN1F", "EXHOSLUSM495S"],
    },
    "EXHOSLUSM495S": {
        "read_format": "**Level (M annualized)** + **MoM%** · YoY% trend",
        "watch_thresholds": "<4M = freeze (rates cao) / 5-5.5M = normal / >6M = boom",
        "release_pattern": "Cuối tháng (~20-23), 10:00 ET",
        "related_indicators": ["HSN1F", "PERMIT", "MBA30Y"],
    },
    "CSUSHPINSA": {
        "read_format": "**YoY%** primary · MoM% momentum · 2-month lag",
        "watch_thresholds": "YoY <0% = housing bust / 0-3% slow / 3-7% healthy / >10% boom",
        "release_pattern": "Cuối tháng (~25), 9:00 ET, lag 2 months",
        "related_indicators": ["USSTHPI", "HOUST", "MBA30Y"],
    },
    "MBA30Y": {
        "read_format": "**Level (%)** · weekly change",
        "watch_thresholds": "<6% = home affordability OK / 6-7% = cooling / >7% = freeze",
        "release_pattern": "Mọi Thứ Tư 7:00 ET",
        "related_indicators": ["DGS10", "MBAAPPS", "HOUST"],
    },

    # ====== FED & RATES ======
    "DFF": {
        "read_format": "**Level (%)** · changes only at FOMC meetings (8/year)",
        "watch_thresholds": "Neutral ~2.5-3% / Restrictive >3.5% / Accommodative <2%",
        "release_pattern": "FOMC: 8 lần/năm. Daily effective rate from NY Fed.",
        "related_indicators": ["DGS2", "DGS10", "T10Y2Y"],
    },
    "DGS10": {
        "read_format": "**Level (%)** · 1D/1W changes for momentum · KHÔNG MoM/YoY",
        "watch_thresholds": "<3% = recession bid / 4-4.5% = neutral / >5% = stress / spike >50bps/week = disruption",
        "release_pattern": "Daily, real-time (US Treasury)",
        "related_indicators": ["DGS2", "T10Y2Y", "T10YIE", "MBA30Y"],
    },
    "DGS2": {
        "read_format": "**Level (%)** · Reflect Fed expectations 2y · Compare with Fed Funds",
        "watch_thresholds": "DGS2 < Fed Funds = market expects cuts / > Fed Funds = expects hikes",
        "release_pattern": "Daily, real-time",
        "related_indicators": ["DFF", "DGS10", "T10Y2Y"],
    },
    "T10Y2Y": {
        "read_format": "**Level (pp)** · Inversion <0 = recession signal · KHÔNG transform",
        "watch_thresholds": ">+1.0% normal steep / 0-1% flatten / **<0 (inverted) = recession trong 6-24 tháng**",
        "release_pattern": "Daily, computed from yields",
        "related_indicators": ["DGS10", "DGS2", "DGS3MO"],
    },

    # ====== CROSS-ASSET (FRED) ======
    "VIXCLS": {
        "read_format": "**Level (Index)** primary · 1D % spike = signal",
        "watch_thresholds": "<15 = complacency / 15-20 = neutral / 20-30 = cautious / >30 = stress / >40 = panic",
        "release_pattern": "Daily, real-time (CBOE close)",
        "related_indicators": ["BAMLH0A0HYM2", "DTWEXBGS", "DGS10"],
    },
    "DTWEXBGS": {
        "read_format": "**Level (Index)** + 1M %",
        "watch_thresholds": "<100 weak / 100-110 normal / >115 strong (xấu cho multinationals)",
        "release_pattern": "Daily, computed by Fed",
        "related_indicators": ["DGS10", "BAMLH0A0HYM2"],
    },
    "DCOILWTICO": {
        "read_format": "**Level (USD/bbl)** + 1W/1M %",
        "watch_thresholds": "<$60 demand weak / $60-90 normal / >$100 inflation pressure / >$120 stagflation risk",
        "release_pattern": "Daily, real-time",
        "related_indicators": ["DCOILBRENTEU", "CPIAUCSL"],
    },
    "BAMLH0A0HYM2": {
        "read_format": "**Level (%)** primary · widen 100bps/week = stress",
        "watch_thresholds": "<3% euphoria / 3-5% neutral / 5-7% caution / >7% stress / >10% panic/recession",
        "release_pattern": "Daily, ICE BofA",
        "related_indicators": ["BAMLC0A0CM", "VIXCLS"],
    },
    "BAMLC0A0CM": {
        "read_format": "**Level (%)** · Stable hơn HY, widen mạnh = systemic risk",
        "watch_thresholds": "<1% risk-on / 1-1.5% neutral / >1.5% caution / >2% stress",
        "release_pattern": "Daily, ICE BofA",
        "related_indicators": ["BAMLH0A0HYM2"],
    },
    "T10YIE": {
        "read_format": "**Level (%)** · = DGS10 - DGS10 TIPS",
        "watch_thresholds": "2-2.5% anchored / >2.5% drift up / <2% deflation risk",
        "release_pattern": "Daily, computed by FRED",
        "related_indicators": ["DGS10", "MICH5Y"],
    },
}

# ============================================================================
# Category defaults — applied to indicators NOT in ENRICHMENTS map.
# ============================================================================
CATEGORY_DEFAULTS = {
    "inflation": {
        "read_format": "**YoY%** primary (trend) · **MoM%** momentum · 3-mo annualized cho Fed view",
        "watch_thresholds": "Phụ thuộc indicator; xem mục good_vs_bad",
        "release_pattern": "Hàng tháng",
        "related_indicators": ["CPIAUCSL", "PCEPILFE"],
    },
    "labor": {
        "read_format": "**MoM%** hoặc Δ (mới quan trọng) · Level (cho rate indicators) · KHÔNG xem cumulative level",
        "watch_thresholds": "Xem mục good_vs_bad",
        "release_pattern": "Weekly hoặc monthly",
        "related_indicators": ["PAYEMS", "UNRATE", "ICSA"],
    },
    "growth": {
        "read_format": "**MoM%** (monthly) hoặc **QoQ annualized %** (quarterly) · YoY% trend",
        "watch_thresholds": "Xem mục good_vs_bad",
        "release_pattern": "Hàng tháng",
        "related_indicators": ["GDPC1", "GDPNOW", "INDPRO"],
    },
    "confidence": {
        "read_format": "**Level (Index)** primary · MoM% momentum",
        "watch_thresholds": "Phụ thuộc index baseline (50 hoặc 100)",
        "release_pattern": "Hàng tháng",
        "related_indicators": ["UMCSENT", "MICH1Y"],
    },
    "housing": {
        "read_format": "**MoM%** + **Level** · YoY% trend",
        "watch_thresholds": "Xem mục good_vs_bad",
        "release_pattern": "Hàng tháng",
        "related_indicators": ["HOUST", "PERMIT", "MBA30Y"],
    },
    "fed": {
        "read_format": "**Level (%)** · KHÔNG transform",
        "watch_thresholds": "Xem mục good_vs_bad",
        "release_pattern": "Daily hoặc theo FOMC schedule",
        "related_indicators": ["DFF", "DGS10", "T10Y2Y"],
    },
    "trade": {
        "read_format": "**Level (B USD)** + **MoM** change · YoY% trend",
        "watch_thresholds": "US thường deficit; thu hẹp = positive GDP",
        "release_pattern": "Hàng tháng",
        "related_indicators": ["BOPGSTB", "GOODSTRADE"],
    },
    "money": {
        "read_format": "**Level** + **YoY%** trend dài hạn",
        "watch_thresholds": "Xem mục good_vs_bad",
        "release_pattern": "Weekly hoặc monthly",
        "related_indicators": ["WALCL", "M2SL"],
    },
    "energy": {
        "read_format": "**Level (M barrels hoặc K)** + **WoW change** (vs forecast)",
        "watch_thresholds": "Big surprise vs forecast = price mover",
        "release_pattern": "Weekly",
        "related_indicators": ["WCESTUS1", "DCOILWTICO"],
    },
}

# ============================================================================
# Glossary — new category "Khái Niệm Cơ Bản" with foundational terms.
# ============================================================================
GLOSSARY = {
    "id": "glossary",
    "name": "Khái Niệm Cơ Bản (Glossary)",
    "indicators": [
        {
            "id": "G_SURPRISE",
            "short_name": "Surprise / Beat / Miss",
            "full_name": "Surprise — Beat / Miss / In-line",
            "frequency": "—",
            "link": "",
            "description": "Khi 1 chỉ số công bố ACTUAL khác FORECAST của consensus analysts: **beat** = actual > forecast (positive surprise), **miss** = actual < forecast (negative surprise), **in-line** = sát forecast (chênh <2% hoặc <0.05).",
            "expectation_meaning": "Market đã price-in forecast. Chỉ phần SURPRISE mới move giá.",
            "good_vs_bad": "Beat/miss tự nó không bullish/bearish — phụ thuộc direction (beat CPI = bearish equities; beat NFP = bullish equities thường).",
            "market_reaction": "Surprise lớn (vd > ±0.5σ) = market move ngay. In-line = ít phản ứng. Pros theo dõi surprise direction + magnitude.",
            "read_format": "—",
            "watch_thresholds": "<0.5σ noise / 0.5-1σ mild / 1-2σ strong / >2σ shock",
            "release_pattern": "Mọi data release đều có forecast cluster",
            "related_indicators": [],
        },
        {
            "id": "G_SIGMA",
            "short_name": "σ (Sigma / Standard Deviation)",
            "full_name": "Standard Deviation (σ) — Surprise Magnitude",
            "frequency": "—",
            "link": "",
            "description": "Đo magnitude của surprise vs forecast distribution. 1σ = std dev của analyst forecasts. 2σ = surprise rất hiếm (~5% xác suất).",
            "expectation_meaning": "Surprise 1σ ≈ rate phổ biến trong 'beat/miss'; 2σ ≈ shock; >3σ ≈ extreme rare.",
            "good_vs_bad": "Càng lớn σ → market move càng mạnh.",
            "market_reaction": "Pros định cỡ position theo expected σ. Surprise 2σ thường tạo break-out kỹ thuật.",
            "read_format": "—",
            "watch_thresholds": "1σ normal / 2σ strong / 3σ shock",
            "release_pattern": "—",
            "related_indicators": [],
        },
        {
            "id": "G_SA_NSA",
            "short_name": "SA / NSA",
            "full_name": "Seasonally Adjusted (SA) vs Not Seasonally Adjusted (NSA)",
            "frequency": "—",
            "link": "https://www.bls.gov/cps/seasfaq.htm",
            "description": "**SA** = data đã loại bỏ seasonal patterns (vd retail spike December, job adds spring). **NSA** = raw data theo lịch.",
            "expectation_meaning": "Hầu hết indicators đang xem là SA. NSA thường used cho long-term trend.",
            "good_vs_bad": "SA giúp so sánh tháng-tháng. NSA cho seasonal context (vd retail YoY NSA mới meaningful Dec vs Jul).",
            "market_reaction": "Đừng so SA và NSA. Đa số headline = SA.",
            "read_format": "Hỏi rõ data source ghi SA hay NSA. Default SA cho US monthly.",
            "watch_thresholds": "—",
            "release_pattern": "—",
            "related_indicators": [],
        },
        {
            "id": "G_HEADLINE_CORE",
            "short_name": "Headline vs Core",
            "full_name": "Headline vs Core (Food & Energy excluded)",
            "frequency": "—",
            "link": "",
            "description": "**Headline** = full basket (gồm thực phẩm + năng lượng — volatile). **Core** = loại bỏ food + energy (sticky inflation gauge).",
            "expectation_meaning": "Fed nhìn Core hơn Headline vì food/energy noise. Trader thường nhìn cả 2.",
            "good_vs_bad": "Core hơn Headline (vd Core CPI 2.5%, Headline 4%) → energy spike tạm thời; Core < Headline kéo dài → disinflation thực.",
            "market_reaction": "Core surprise > Headline surprise → react mạnh hơn (Fed-relevant).",
            "read_format": "Cả 2 nên xem YoY. Compare diff.",
            "watch_thresholds": "—",
            "release_pattern": "—",
            "related_indicators": ["CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE"],
        },
        {
            "id": "G_HARD_SURVEY",
            "short_name": "Hard data vs Survey",
            "full_name": "Hard Data vs Soft Data (Survey)",
            "frequency": "—",
            "link": "",
            "description": "**Hard data** = số đo được (NFP, Retail Sales, CPI từ BLS/BEA). **Soft data / Survey** = ý kiến (ISM PMI, Michigan, NFIB).",
            "expectation_meaning": "Hard data lag hơn Survey. Survey lead hard data 1-3 tháng.",
            "good_vs_bad": "Divergence: Survey weak nhưng Hard data strong = consumer/biz lo nhưng vẫn chi. Vice versa = lo hard data follow soft.",
            "market_reaction": "Trader weight hard data cao hơn cho regime calls; soft data cho early signals.",
            "read_format": "—",
            "watch_thresholds": "—",
            "release_pattern": "—",
            "related_indicators": ["PAYEMS", "RSAFS", "UMCSENT", "NFIB"],
        },
        {
            "id": "G_REAL_NOMINAL",
            "short_name": "Real vs Nominal",
            "full_name": "Real (Inflation-Adjusted) vs Nominal",
            "frequency": "—",
            "link": "",
            "description": "**Nominal** = giá trị USD hiện tại. **Real** = đã trừ inflation (purchasing power).",
            "expectation_meaning": "Real = sức mua thật. Nominal growth 5% với CPI 4% = Real 1% (yếu).",
            "good_vs_bad": "Real growth dương = economy thật sự khoẻ. Real âm = bị inflation nuốt.",
            "market_reaction": "Real Retail Sales, Real PCE, Real Earnings → metric quan trọng cho consumer thesis.",
            "read_format": "Khi có data Nominal + Real, **luôn ưu tiên Real**.",
            "watch_thresholds": "—",
            "release_pattern": "—",
            "related_indicators": ["PCE", "RSAFS", "REALEARN"],
        },
        {
            "id": "G_YOY_MOM_QOQ",
            "short_name": "YoY / MoM / QoQ Ann.",
            "full_name": "Year-over-Year / Month-over-Month / Quarter-over-Quarter Annualized",
            "frequency": "—",
            "link": "",
            "description": "**YoY%** so cùng kỳ năm trước (trend dài). **MoM%** so tháng trước (momentum gần). **QoQ ann.** = 4 quý quy năm (cho GDP).",
            "expectation_meaning": "YoY noise ít, lag. MoM signal sớm hơn, noise nhiều. QoQ ann. only meaningful for quarterly series.",
            "good_vs_bad": "Pros nhìn cả 3 để hiểu: YoY = vị trí trend, MoM = momentum gần, 3-mo annualized = 'Fed view'.",
            "market_reaction": "MoM surprise move giá nhanh; YoY confirm regime.",
            "read_format": "—",
            "watch_thresholds": "—",
            "release_pattern": "—",
            "related_indicators": [],
        },
        {
            "id": "G_3MO_ANN",
            "short_name": "3-Month Annualized",
            "full_name": "3-Month Annualized Rate",
            "frequency": "—",
            "link": "",
            "description": "Tăng trưởng 3 tháng gần nhất quy thành tỷ lệ năm. Công thức: ((latest/3mo_ago)^4 − 1) × 100.",
            "expectation_meaning": "Fed dùng cho Core PCE để judge 'momentum gần' (vs YoY lag). Quan trọng cho inflation reads.",
            "good_vs_bad": "3-mo annualized > YoY → đang tăng tốc. < YoY → giảm tốc.",
            "market_reaction": "Powell cite 3-mo annualized rất nhiều trong press conferences post-FOMC.",
            "read_format": "—",
            "watch_thresholds": "Core PCE 3-mo >4% = hawkish urgency / <2.5% = cuts khả thi",
            "release_pattern": "—",
            "related_indicators": ["PCEPILFE", "CPILFESL"],
        },
        {
            "id": "G_REVISION",
            "short_name": "Revisions",
            "full_name": "Data Revisions",
            "frequency": "—",
            "link": "",
            "description": "Khi 1 series được revise (BLS revise NFP T+1, T+2 tháng; BEA revise GDP 3 lần). Initial release thường được revise.",
            "expectation_meaning": "Initial number = best guess. Revisions = refinement. NFP có thể revise ±50K. GDP advance vs final ±0.5%.",
            "good_vs_bad": "Watch revision direction: nếu series consistently revised down = momentum yếu hơn initial reports.",
            "market_reaction": "Revisions ít market mover trừ khi quá lớn (vd 2024 NFP revision -800K → market shock).",
            "read_format": "Khi tracking trend → dùng revised data. Khi tracking surprise → dùng initial release.",
            "watch_thresholds": "—",
            "release_pattern": "—",
            "related_indicators": ["PAYEMS", "GDPC1"],
        },
        {
            "id": "G_FORECAST_CONSENSUS",
            "short_name": "Forecast / Consensus",
            "full_name": "Analyst Forecast / Consensus Estimate",
            "frequency": "—",
            "link": "",
            "description": "Bloomberg/Reuters polls ~50-100 analysts trước mỗi release. Median = consensus. Range = uncertainty.",
            "expectation_meaning": "Market price = consensus. Move chỉ khi actual ≠ consensus.",
            "good_vs_bad": "Consensus tight (range hẹp) → surprise dễ shock. Consensus wide → surprise expected.",
            "market_reaction": "Trader thường so actual vs consensus, KHÔNG so actual vs previous.",
            "read_format": "—",
            "watch_thresholds": "—",
            "release_pattern": "—",
            "related_indicators": [],
        },
        {
            "id": "G_FRONT_RUNNING",
            "short_name": "Front-running / Whisper Number",
            "full_name": "Front-running & Whisper Number",
            "frequency": "—",
            "link": "",
            "description": "**Front-running** = position trước release theo intuition. **Whisper** = unofficial expectation từ trading community (thường khác consensus).",
            "expectation_meaning": "Khi Whisper khác Consensus, actual matching Whisper sẽ react khác matching Consensus.",
            "good_vs_bad": "Pros theo dõi 'whisper > consensus' để gauge positioning skew.",
            "market_reaction": "—",
            "read_format": "—",
            "watch_thresholds": "—",
            "release_pattern": "—",
            "related_indicators": [],
        },
        {
            "id": "G_RISK_ON_OFF",
            "short_name": "Risk-on / Risk-off",
            "full_name": "Risk-on vs Risk-off Regime",
            "frequency": "—",
            "link": "",
            "description": "**Risk-on** = market embraces risk (equities up, HY tight, VIX low). **Risk-off** = flight to safety (bonds up, USD up, VIX up, equities down).",
            "expectation_meaning": "Cluster: VIX, HY spread, USD, gold, BTC, equity sectors all confirm together.",
            "good_vs_bad": "Risk-on bullish equities (Tech/Discretionary lead). Risk-off bullish bonds + defensives (Staples/Healthcare/Utilities).",
            "market_reaction": "—",
            "read_format": "—",
            "watch_thresholds": "VIX <15 + HY <3% = risk-on extreme / VIX >25 + HY >5% = risk-off",
            "release_pattern": "—",
            "related_indicators": ["VIXCLS", "BAMLH0A0HYM2", "DTWEXBGS"],
        },
        {
            "id": "G_DCF_DURATION",
            "short_name": "DCF / Duration",
            "full_name": "Discounted Cash Flow (DCF) — Duration Sensitivity",
            "frequency": "—",
            "link": "",
            "description": "Stock value = discounted future cash flows. Yields tăng → discount factor lớn hơn → present value xuống.",
            "expectation_meaning": "Long-duration assets (Tech, REITs, Utilities) nhạy với yields nhất. Short-duration (Energy, Financials) ít nhạy.",
            "good_vs_bad": "10Y yield giảm 50bps → XLK +3-5%; tăng 50bps → XLK -3-5%.",
            "market_reaction": "Cross-check sector RS với yields. Divergence (vd XLK rally khi yields tăng) = AI narrative override macro.",
            "read_format": "—",
            "watch_thresholds": "—",
            "release_pattern": "—",
            "related_indicators": ["DGS10", "T10YIE"],
        },
        {
            "id": "G_HAWKISH_DOVISH",
            "short_name": "Hawkish / Dovish",
            "full_name": "Fed Stance: Hawkish vs Dovish",
            "frequency": "—",
            "link": "",
            "description": "**Hawkish** = Fed muốn giữ rate cao / không cut (fight inflation). **Dovish** = Fed sẵn sàng cut (support growth/jobs).",
            "expectation_meaning": "Powell speeches + FOMC statements + dot plot → judge stance.",
            "good_vs_bad": "Hawkish: yields up, USD up, XLK pressure. Dovish: yields down, USD down, XLK rally.",
            "market_reaction": "Most market-moving events: Powell post-FOMC press conf, Jackson Hole.",
            "read_format": "—",
            "watch_thresholds": "—",
            "release_pattern": "FOMC 8x/year + speakers monthly",
            "related_indicators": ["DFF", "DGS2", "DGS10"],
        },
        {
            "id": "G_CLUSTER_READ",
            "short_name": "Cluster Reads",
            "full_name": "Cluster Reads — 1 data point ≠ trend",
            "frequency": "—",
            "link": "",
            "description": "Single data point = noise (1 month NFP -50K không phải recession). Cần ≥2 indicators cùng signal mới reliable.",
            "expectation_meaning": "Vd 'labor cracking' chỉ confirm khi ICSA tăng + Challenger spike + ADP yếu + NFP miss đồng thời.",
            "good_vs_bad": "Pros chờ cluster confirm trước khi rebalance. Amateurs react single data → whipsaw.",
            "market_reaction": "—",
            "read_format": "Luôn nhìn cluster, không nhìn single data point.",
            "watch_thresholds": "—",
            "release_pattern": "—",
            "related_indicators": [],
        },
    ],
}


def main() -> int:
    if not THEORY.exists():
        print(f"theory missing: {THEORY}", file=sys.stderr)
        return 1

    theory = json.loads(THEORY.read_text())
    fields = ["read_format", "watch_thresholds", "release_pattern", "related_indicators"]

    enriched = 0
    defaulted = 0
    skipped = 0
    for cat in theory["categories"]:
        cat_id = cat.get("id", "")
        defaults = CATEGORY_DEFAULTS.get(cat_id, {})
        for ind in cat["indicators"]:
            ind_id = ind.get("id", "")
            # Skip if all 4 fields already present
            if all(f in ind for f in fields):
                skipped += 1
                continue
            # Prefer specific enrichment
            specific = ENRICHMENTS.get(ind_id)
            source = specific if specific else defaults
            if not source:
                continue
            for f in fields:
                if f not in ind and f in source:
                    ind[f] = source[f]
            if specific:
                enriched += 1
            else:
                defaulted += 1

    # Add Glossary category if not exists
    existing_cat_ids = {c.get("id") for c in theory["categories"]}
    if GLOSSARY["id"] not in existing_cat_ids:
        theory["categories"].append(GLOSSARY)
        added_glossary = len(GLOSSARY["indicators"])
    else:
        added_glossary = 0

    THEORY.write_text(json.dumps(theory, indent=2, ensure_ascii=False))
    total = sum(len(c["indicators"]) for c in theory["categories"])
    print(f"Enriched {enriched} indicators with specific content")
    print(f"Defaulted {defaulted} indicators based on category")
    print(f"Skipped {skipped} (already had all 4 fields)")
    if added_glossary:
        print(f"Added new category 'Glossary' with {added_glossary} concepts")
    print(f"Total: {total} indicators across {len(theory['categories'])} categories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
