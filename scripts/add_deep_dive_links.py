#!/usr/bin/env python3
"""Add deep_dive_link to every indicator in data/macro_theory.json.

deep_dive_link → official agency interactive chart / release page that shows
sub-component breakdowns (e.g., CPI by shelter/food/energy/services).
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent
THEORY = ROOT / "data" / "macro_theory.json"

# Map indicator id → deep_dive_link (best interactive chart / detail page).
# NOTE: BLS, DOL, S&P Global, MBA block bots (curl/HTTP 403) but the pages load
# fine in a real browser. We deliberately use canonical, long-stable URLs
# (news.release/*.htm, product hubs) verified to exist — NOT fabricated slugs.
DEEP_DIVE = {
    # ── INFLATION ──────────────────────────────────────────────────────────────
    # BLS CPI news release: full category tables (food, energy, shelter, services)
    "CPIAUCSL": "https://www.bls.gov/news.release/cpi.htm",
    "CPILFESL": "https://www.bls.gov/news.release/cpi.htm",
    "PCEPI":    "https://apps.bea.gov/iTable/?ReqID=19&step=4&isuri=1&categories=survey&nipa_table_list=71",
    "PCEPILFE": "https://apps.bea.gov/iTable/?ReqID=19&step=4&isuri=1&categories=survey&nipa_table_list=71",
    "PPIFID":   "https://www.bls.gov/news.release/ppi.htm",
    "PPIFES":   "https://www.bls.gov/news.release/ppi.htm",
    "MEDCPIM158SFRBCLE": "https://www.clevelandfed.org/our-research/indicators-and-data/median-cpi",
    "REALEARN": "https://www.bls.gov/news.release/realer.htm",

    # ── LABOR ──────────────────────────────────────────────────────────────────
    # BLS Employment Situation: Table B-1 = employment change by industry
    "PAYEMS":         "https://www.bls.gov/news.release/empsit.htm",
    "UNRATE":         "https://www.bls.gov/news.release/empsit.htm",
    "ICSA":           "https://oui.doleta.gov/unemploy/claims.asp",
    "CES0500000003":  "https://www.bls.gov/news.release/empsit.htm",
    "JTSJOL":         "https://www.bls.gov/news.release/jolts.htm",
    "CCSA":           "https://oui.doleta.gov/unemploy/claims.asp",
    "IC4WSA":         "https://oui.doleta.gov/unemploy/claims.asp",
    "ADPMNUSNERNSA":  "https://adpemploymentreport.com/",
    "CHALLENGER":     "https://www.challengergray.com/blog/",
    "OPHNFB":         "https://www.bls.gov/news.release/prod2.htm",
    "ULCNFB":         "https://www.bls.gov/news.release/prod2.htm",
    "CIVPART":        "https://www.bls.gov/news.release/empsit.htm",
    "U6RATE":         "https://www.bls.gov/news.release/empsit.htm",
    "AWHAETP":        "https://www.bls.gov/news.release/empsit.htm",
    "CES9091000001":  "https://www.bls.gov/news.release/empsit.htm",
    "MANEMP":         "https://www.bls.gov/news.release/empsit.htm",
    "CES0500000008":  "https://www.bls.gov/news.release/empsit.htm",
    "CETI":           "https://www.conference-board.org/data/employmenttrends.cfm",
    "NYFED1YINFL":    "https://www.newyorkfed.org/microeconomics/sce/chart-gallery",

    # ── GROWTH ─────────────────────────────────────────────────────────────────
    # GDP: BEA NIPA interactive tables (PCE, Gross Private Investment, Gov, Net Exports)
    "GDPC1":       "https://apps.bea.gov/iTable/?ReqID=19&step=4&isuri=1&categories=survey&nipa_table_list=1",
    "RSAFS":       "https://www.census.gov/retail/index.html",
    "NAPM":        "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/",
    "NAPMNMI":     "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/",
    "GDPNOW":      "https://www.atlantafed.org/cqer/research/gdpnow",
    "SPGLOBALMFG": "https://www.spglobal.com/marketintelligence/en/mi/products/pmi.html",
    "SPGLOBALSVC": "https://www.spglobal.com/marketintelligence/en/mi/products/pmi.html",
    "SPGLOBALCOMP":"https://www.spglobal.com/marketintelligence/en/mi/products/pmi.html",
    "CHICAGOPMI":  "https://www.ism-chicago.org/",
    "ISMMFGNEW":   "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/",
    "ISMMFGPRICES":"https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/",
    "ISMMFGEMP":   "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/",
    "NEWORDER":    "https://www.census.gov/manufacturing/m3/index.html",
    "DGORDER":     "https://www.census.gov/manufacturing/m3/index.html",
    "TTLCONS":     "https://www.census.gov/construction/c30/c30index.html",
    "INDPRO":      "https://www.federalreserve.gov/releases/g17/current/default.htm",
    # Personal Income & Spending: BEA NIPA Table 2.3.5 (PCE by type) — goods/services
    "PI":          "https://apps.bea.gov/iTable/?ReqID=19&step=4&isuri=1&categories=survey&nipa_table_list=58",
    "PCE":         "https://apps.bea.gov/iTable/?ReqID=19&step=4&isuri=1&categories=survey&nipa_table_list=58",
    "TOTALSA":     "https://www.bea.gov/data/consumer-spending/main",
    "WHLSLRIMSA":  "https://www.census.gov/wholesale/index.html",
    "RETAILINV":   "https://www.census.gov/retail/index.html",
    "GOODSTRADE":  "https://www.census.gov/foreign-trade/index.html",
    "CFNAI":       "https://www.chicagofed.org/research/data/cfnai/current-data",
    "RICHMONDMFG": "https://www.richmondfed.org/research/data_analysis",
    "DALLASMFG":   "https://www.dallasfed.org/research/surveys/tmos",
    "CORPPROFITS": "https://www.bea.gov/data/income-saving/corporate-profits",
    "ISMSVCBA":    "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/",

    # ── CONFIDENCE ─────────────────────────────────────────────────────────────
    "CSCICP03USM665S": "https://www.conference-board.org/topics/consumer-confidence",
    # Michigan: interactive chart page shows all 5 sub-indices (Sentiment, Current, Expectations, 1Y, 5Y inflation)
    "UMCSENT":  "https://data.sca.isr.umich.edu/charts.html",
    "MICHCURR": "https://data.sca.isr.umich.edu/charts.html",
    "MICHEXP":  "https://data.sca.isr.umich.edu/charts.html",
    "MICH1Y":   "https://data.sca.isr.umich.edu/charts.html",
    "MICH5Y":   "https://data.sca.isr.umich.edu/charts.html",
    "NFIB":     "https://www.nfib.com/surveys/small-business-economic-trends/",
    "IBDTIPP":  "https://www.tipponline.com/",
    "IPSOSPCSI":"https://www.ipsos.com/en-us",

    # ── HOUSING ────────────────────────────────────────────────────────────────
    "HOUST":           "https://www.census.gov/construction/nrc/index.html",
    "EXHOSLUSM495S":   "https://www.nar.realtor/research-and-statistics/housing-statistics/existing-home-sales",
    "PERMIT":          "https://www.census.gov/construction/nrc/index.html",
    "HSN1F":           "https://www.census.gov/construction/nrs/index.html",
    "USSTHPI":         "https://www.fhfa.gov/DataTools/Downloads/Pages/House-Price-Index.aspx",
    "CSCH20":          "https://www.spglobal.com/spdji/en/index-family/indicators/sp-corelogic-case-shiller/",
    "MBA30Y":          "https://www.mba.org/news-and-research/research-and-economics",
    "MBAAPPS":         "https://www.mba.org/news-and-research/research-and-economics",

    # ── FED ────────────────────────────────────────────────────────────────────
    "DFF":   "https://www.federalreserve.gov/monetarypolicy/openmarket.htm",
    # Treasury yield curve — full curve 1M to 30Y, daily
    "DGS10": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve",
    "DGS2":  "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve",

    # ── TRADE ──────────────────────────────────────────────────────────────────
    "BOPGSTB": "https://www.bea.gov/data/intl-trade-investment/international-trade-goods-and-services",
    "EXPGS":   "https://www.bea.gov/data/intl-trade-investment/international-trade-goods-and-services",
    "IMPGS":   "https://www.bea.gov/data/intl-trade-investment/international-trade-goods-and-services",

    # ── MONEY ──────────────────────────────────────────────────────────────────
    "M2SL":    "https://www.federalreserve.gov/releases/h6/current/default.htm",
    "WALCL":   "https://www.federalreserve.gov/releases/h41/current/default.htm",
    "WRESBAL": "https://www.federalreserve.gov/releases/h41/current/default.htm",
    "TOTALSL": "https://www.federalreserve.gov/releases/g19/current/default.htm",
    "MTSDS":   "https://www.fiscal.treasury.gov/reports-statements/mts/",
    "REDBOOK": "https://www.redbookresearch.com/",

    # ── ENERGY ─────────────────────────────────────────────────────────────────
    # EIA Petroleum Supply Weekly — shows crude, gasoline, distillates, refinery utilization all-in-one
    "WCESTUS1":           "https://www.eia.gov/petroleum/supply/weekly/",
    "APICRUDE":           "https://www.api.org/products-and-services/statistics/weekly-statistical-bulletin",
    "NATGAS":             "https://www.eia.gov/naturalgas/weekly/",
    "BAKERHUGHES":        "https://rigcount.bakerhughes.com/",
    "EIA_REFINERY_RUNS":  "https://www.eia.gov/petroleum/supply/weekly/",
    "EIA_DISTILLATES_STOCKS": "https://www.eia.gov/petroleum/supply/weekly/",
    "EIA_GASOLINE_PROD":  "https://www.eia.gov/petroleum/supply/weekly/",
    "EIA_GASOLINE_INV":   "https://www.eia.gov/petroleum/supply/weekly/",
    "EIA_REFINERY_UTIL":  "https://www.eia.gov/petroleum/supply/weekly/",
    "EIA_STEO":           "https://www.eia.gov/outlooks/steo/",
}

def patch():
    data = json.loads(THEORY.read_text(encoding="utf-8"))
    patched = 0
    skipped = 0
    for cat in data["categories"]:
        for ind in cat["indicators"]:
            iid = ind["id"]
            if iid in DEEP_DIVE:
                ind["deep_dive_link"] = DEEP_DIVE[iid]
                patched += 1
            else:
                skipped += 1  # glossary entries — no data link needed
    THEORY.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Patched {patched} indicators, skipped {skipped} (glossary/unmapped)")

if __name__ == "__main__":
    patch()
