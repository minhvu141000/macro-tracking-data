#!/usr/bin/env python3
"""Collect US macro data for a given date.

Sources:
- investing.com economic calendar (scraped via their public AJAX endpoint)
- FRED API (St. Louis Fed) for historical series

Output: data/raw/<date>.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()
# Free key: register at https://api.census.gov/data/key_signup.html (instant, no cost)
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY", "").strip()

# Core FRED series we always snapshot
FRED_SERIES = {
    # Inflation
    "CPIAUCSL": "CPI All Items",
    "CPILFESL": "Core CPI",
    "PCEPI": "PCE Price Index",
    "PCEPILFE": "Core PCE",
    # PPI: investing.com headline = "PPI Final Demand" (PPIFID), NOT All Commodities
    # (PPIACO). PPIACO YoY ~13% misleads — Final Demand YoY ~6.5% matches the release.
    "PPIFID": "PPI Final Demand",
    "PPIFES": "Core PPI (Final Demand ex Food & Energy)",
    # CPI sub-components — analyst uses for breakdown on CPI day (index levels, MoM/YoY derived)
    "CUSR0000SAH1": "CPI Shelter",
    "CPIUFDSL": "CPI Food",
    "CPIENGSL": "CPI Energy",
    "CUSR0000SACL1E": "CPI Core Goods (ex Food & Energy)",
    "CUSR0000SASLE": "CPI Core Services (ex Energy)",
    # Labor — headline
    "PAYEMS": "Nonfarm Payrolls",
    "UNRATE": "Unemployment Rate",
    "ICSA": "Initial Jobless Claims",
    "CES0500000003": "Avg Hourly Earnings",
    "JTSJOL": "Job Openings (JOLTS)",
    # Labor — sector payrolls (MoM Δ meaningful on NFP days)
    "USCONS": "Payrolls: Construction",
    "USFIRE": "Payrolls: Financial Activities",
    "USLAH": "Payrolls: Leisure and Hospitality",
    "USPBS": "Payrolls: Professional and Business Services",
    "USEHS": "Payrolls: Education and Health Services",
    "USTRADE": "Payrolls: Retail Trade",
    "USINFO": "Payrolls: Information",
    # Labor — unemployment by race/ethnicity (BLS via FRED, SA)
    "LNS14000003": "Unemployment Rate: White",
    "LNS14000006": "Unemployment Rate: Black or African American",
    "LNS14000009": "Unemployment Rate: Hispanic or Latino",
    "LNS14032183": "Unemployment Rate: Asian",
    # Labor — full-time vs part-time
    "LNS12500000": "Employment: Usually Work Full Time",
    "LNS13023621": "Employment: Part-Time for Economic Reasons",
    # Trade (BEA Balance of Payments basis, monthly — historical trend context)
    "BOPGSTB": "Trade Balance: Goods & Services (BOP)",
    # Import/Export price indexes (BLS, monthly) — imported-inflation channel
    "IR": "Import Price Index (End Use: All Commodities)",
    "IQ": "Export Price Index (End Use: All Commodities)",
    # Growth
    # GDP: investing.com headline = QoQ annualized growth RATE (e.g. +1.6%), not the
    # level in $B. A191RL1Q225SBEA is already that rate → chart it directly (view=level).
    "A191RL1Q225SBEA": "Real GDP Growth (QoQ ann.)",
    # GDP attribution — contribution to real GDP growth (percentage points, annual
    # rate). These 4 SUM to the headline GDP rate (A191RL1Q225SBEA) → directly show
    # which engine is pulling GDP up vs dragging it down. Read `latest.value` (= pp).
    "DPCERY2Q224SBEA": "GDP Contribution: Consumer Spending (PCE)",
    "A006RY2Q224SBEA": "GDP Contribution: Private Investment",
    "A019RY2Q224SBEA": "GDP Contribution: Net Exports",
    "A822RY2Q224SBEA": "GDP Contribution: Government",
    "RSAFS": "Retail Sales",
    # Retail Sales sub-component
    "RSFSXMV": "Retail Sales ex-Motor Vehicles",
    "INDPRO": "Industrial Production",
    "MANEMP": "Manufacturing Employment",
    "BSCICP03USM665S": "Business Confidence",
    "TTLCONS": "Total Construction Spending",
    "GDPNOW": "Atlanta Fed GDPNow",
    "DGORDER": "Durable Goods Orders",
    # Sentiment
    "UMCSENT": "Michigan Consumer Sentiment",
    "CSCICP03USM665S": "Consumer Confidence",
    # Housing
    "HOUST": "Housing Starts",
    "EXHOSLUSM495S": "Existing Home Sales",
    "CSUSHPINSA": "Case-Shiller Home Price",
    # Fed / rates
    "DFF": "Fed Funds Rate",
    "DGS10": "10Y Treasury Yield",
    "DGS2": "2Y Treasury Yield",
    "DGS3MO": "3M Treasury Yield",
    "DGS6MO": "6M Treasury Yield",
    "T10Y2Y": "10Y-2Y Spread",
    # Cross-asset context
    "DTWEXBGS": "USD Index (Broad)",
    "VIXCLS": "VIX (Volatility Index)",
    "DCOILWTICO": "WTI Crude Oil",
    "BAMLH0A0HYM2": "High-Yield Credit Spread (HY OAS)",
    "BAMLC0A0CM": "Investment-Grade Credit Spread (IG OAS)",
    "T10YIE": "10Y Inflation Breakeven",
}

INVESTING_AJAX = "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"
INVESTING_PAGE = "https://www.investing.com/economic-calendar/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def fetch_fred_series(series_id: str, observations: int = 120) -> list[dict[str, Any]]:
    """Fetch recent observations for a FRED series. Returns list of {date, value}.

    Throttle + exponential backoff on 429. FRED limit is 120 req/min — we sleep
    0.6s between successful calls and back off if rate-limited.
    """
    if not FRED_API_KEY:
        return []
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": observations,
    }
    delays = [0.6, 2.0, 5.0]  # retry waits
    for attempt, wait in enumerate([0] + delays):
        if wait:
            time.sleep(wait)
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 429:
                if attempt < len(delays):
                    continue  # retry with longer backoff
                print(f"  FRED 429 for {series_id} (all retries exhausted)", file=sys.stderr)
                return []
            r.raise_for_status()
            obs = r.json().get("observations", [])
            out = []
            for o in obs:
                val = o.get("value")
                if val in (".", None, ""):
                    continue
                try:
                    out.append({"date": o["date"], "value": float(val)})
                except (ValueError, TypeError):
                    continue
            out.reverse()  # chronological
            time.sleep(0.6)  # throttle to stay well under 120 req/min
            return out
        except Exception as exc:
            if attempt < len(delays):
                continue
            print(f"  FRED error for {series_id}: {exc}", file=sys.stderr)
            return []
    return []


def _compute_derived_metrics(history: list[dict]) -> dict[str, Any]:
    """Pre-compute YoY, MoM, 3-mo annualized so analyst doesn't need full history.

    Frequency detection from gap between last 2 observations:
    - < 10 days → daily series → use 252 trading days for YoY
    - 10-80 days → monthly → use 12 obs for YoY
    - > 80 days → quarterly → use 4 obs for YoY
    """
    if len(history) < 2:
        return {}
    out = {}
    latest = history[-1]
    prev = history[-2]

    # Detect frequency
    from datetime import date as _date
    try:
        t1 = _date.fromisoformat(latest["date"])
        t0 = _date.fromisoformat(prev["date"])
        gap_days = (t1 - t0).days
    except Exception:
        gap_days = 30

    if gap_days < 10:
        yoy_lag = 252
        freq = "daily"
    elif gap_days < 80:
        yoy_lag = 12
        freq = "monthly"
    else:
        yoy_lag = 4
        freq = "quarterly"

    out["frequency"] = freq

    # MoM (or daily-on-daily) change %
    if prev["value"] not in (0, None):
        out["mom_pct"] = round((latest["value"] - prev["value"]) / prev["value"] * 100, 3)

    # YoY
    if len(history) > yoy_lag:
        year_ago = history[-yoy_lag - 1]
        if year_ago["value"] not in (0, None):
            out["yoy_pct"] = round((latest["value"] - year_ago["value"]) / year_ago["value"] * 100, 2)

    # 3-period annualized (monthly only — meaningful concept)
    if freq == "monthly" and len(history) > 3:
        three_ago = history[-4]
        if three_ago["value"] not in (0, None):
            three_mo_change = (latest["value"] / three_ago["value"]) ** 4 - 1
            out["mo3_annualized_pct"] = round(three_mo_change * 100, 2)

    return out


def fetch_fred_snapshot() -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch latest values + history for all core series.

    Returns (trimmed, full):
    - trimmed: small snapshot for daily raw JSON (last 3 obs + pre-computed YoY/MoM/3mo)
    - full: full history for separate fred_history.json (overwrite daily)

    This dual output lets LLM analyst read a compact ~9-12K token raw JSON while the
    dashboard still has 10y history for charts (via separate file).
    """
    trimmed: dict[str, Any] = {}
    full: dict[str, Any] = {}
    for series_id, label in FRED_SERIES.items():
        history = fetch_fred_series(series_id)
        if not history:
            empty = {"label": label, "latest": None, "history": []}
            trimmed[series_id] = empty
            full[series_id] = empty
            continue
        latest = history[-1]
        prev = history[-2] if len(history) > 1 else None
        change_pct = (
            round((latest["value"] - prev["value"]) / prev["value"] * 100, 3)
            if prev and prev["value"] not in (0, None)
            else None
        )
        derived = _compute_derived_metrics(history)

        common = {
            "label": label,
            "latest": latest,
            "previous": prev,
            "change_pct": change_pct,
            **derived,
        }
        # Trimmed: last 3 observations only. The analyst reads pre-computed
        # latest/previous/mom_pct/yoy_pct/mo3_annualized_pct above — it almost never
        # needs raw history, so 3 obs (≈ last quarter for monthly series) is plenty
        # for a quick "last few prints" sanity check. Saves ~7K tokens vs 20 obs.
        # Dashboard charts read full history from the separate fred_history.json.
        trimmed[series_id] = {**common, "history": history[-3:]}
        # Full: complete history for dashboard charting
        full[series_id] = {**common, "history": history}
    return trimmed, full


def scrape_investing_calendar(target: date) -> list[dict[str, Any]]:
    """Scrape investing.com economic calendar via Playwright (headless Chromium).

    Plain HTTP clients can't get past Cloudflare's `cf_clearance` cookie (requires
    JavaScript challenge). Playwright runs real Chromium → executes JS → gets
    clearance → can POST the AJAX endpoint.

    Flow:
      1. Launch headless Chromium with realistic UA.
      2. Navigate to /economic-calendar/ — JS runs, cf_clearance set.
      3. Use page.request (carries cookies) to POST getCalendarFilteredData.
      4. Parse HTML fragment with BeautifulSoup.

    NOTE: investing.com geo-blocks some countries (e.g. Vietnam) at network layer
    — Playwright won't help there. From US/EU/Canada it works.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  playwright not installed — run `pip install playwright && python -m playwright install chromium`", file=sys.stderr)
        return []

    body_form = {
        "country[]": "5",
        "importance[]": ["1", "2", "3"],
        "timeZone": "8",
        "timeFilter": "timeRemain",
        "currentTab": "custom",
        "dateFrom": target.isoformat(),
        "dateTo": target.isoformat(),
        "limit_from": "0",
    }
    # Build form-urlencoded body (Playwright APIRequest expects string for form posts)
    from urllib.parse import urlencode
    form_string = urlencode(body_form, doseq=True)

    html_fragment = ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1366, "height": 800},
                locale="en-US",
            )
            page = context.new_page()
            # Navigate to calendar page — Cloudflare JS challenge runs here
            page.goto(INVESTING_PAGE, wait_until="domcontentloaded", timeout=30000)
            # Wait a moment for Cloudflare to finish (cf_clearance set)
            page.wait_for_timeout(2500)
            # Now POST AJAX using page.request — it carries context cookies
            resp = context.request.post(
                INVESTING_AJAX,
                headers={
                    "Accept": "*/*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": INVESTING_PAGE,
                    "X-Requested-With": "XMLHttpRequest",
                    "Origin": "https://www.investing.com",
                },
                data=form_string,
                timeout=25000,
            )
            if resp.status != 200:
                print(f"  investing.com POST returned HTTP {resp.status}", file=sys.stderr)
                browser.close()
                return []
            try:
                payload = resp.json()
                html_fragment = payload.get("data", "")
            except Exception:
                html_fragment = resp.text()
            browser.close()
    except Exception as exc:
        print(f"  Playwright scrape failed: {exc}", file=sys.stderr)
        return []

    return _parse_calendar_rows(html_fragment, target)


def _parse_calendar_rows(html_fragment: str, target: date) -> list[dict[str, Any]]:
    """Parse the HTML fragment returned by getCalendarFilteredData."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("  bs4 not installed", file=sys.stderr)
        return []

    soup = BeautifulSoup(html_fragment, "html.parser")
    rows = soup.select("tr.js-event-item")
    out = []
    target_iso = target.isoformat()
    for row in rows:
        dt = row.get("data-event-datetime", "")
        dt_iso = dt.replace("/", "-").split(" ")[0]
        if dt_iso and dt_iso != target_iso:
            continue
        name_a_el = row.select_one(".event a")
        name_el = name_a_el or row.select_one(".event")
        actual_el = row.select_one(".act")
        forecast_el = row.select_one(".fore")
        prev_el = row.select_one(".prev")
        importance_el = row.select_one(".sentiment")

        def _txt(el: Any) -> str | None:
            if not el:
                return None
            t = el.get_text(strip=True)
            return t if t and t != "\xa0" else None

        # Build investing.com event URL if anchor exists
        event_url = None
        if name_a_el and name_a_el.get("href"):
            href = name_a_el["href"]
            event_url = href if href.startswith("http") else f"https://www.investing.com{href}"

        out.append(
            {
                "name": _txt(name_el),
                "time": dt,
                "importance": importance_el.get("data-img_key") if importance_el else None,
                "actual": _txt(actual_el),
                "forecast": _txt(forecast_el),
                "previous": _txt(prev_el),
                "event_url": event_url,
                "source": "investing.com",
            }
        )
    return out


CENSUS_TRADE_URL = "https://api.census.gov/data/timeseries/intltrade"


def _census_get(flow: str, params: dict[str, str]) -> list[list] | None:
    """Call Census Bureau intltrade API. Returns rows (list-of-lists) or None."""
    if not CENSUS_API_KEY:
        return None
    try:
        r = requests.get(
            f"{CENSUS_TRADE_URL}/{flow}",
            params={"key": CENSUS_API_KEY, **params},
            timeout=25,
            headers={"User-Agent": USER_AGENT},
        )
        if r.status_code != 200:
            print(f"  Census {flow}: HTTP {r.status_code}", file=sys.stderr)
            return None
        data = r.json()
        return data if data and len(data) > 1 else None
    except Exception as exc:
        print(f"  Census {flow} error: {exc}", file=sys.stderr)
        return None


def fetch_census_trade_detail(target: date) -> dict[str, Any]:
    """Fetch US import breakdown by country + end-use from Census Bureau API (no key needed).

    Reference month = 2 months prior (Census FT-900 lags ~5 weeks after month end).
    Aggregates rows by country (Census returns one row per country×commodity combination).
    Returns {} on any failure — non-blocking optional enrichment.
    All monetary values in thousands of USD.
    """
    ref_m = target.month - 2
    ref_y = target.year
    if ref_m <= 0:
        ref_m += 12
        ref_y -= 1
    prev_y = ref_y - 1
    ref_label = f"{ref_y}-{ref_m:02d}"

    if not CENSUS_API_KEY:
        print("  Census trade: CENSUS_API_KEY not set — skipping (register free at api.census.gov/data/key_signup.html)", file=sys.stderr)
        return {}
    print(f"  Census trade detail → reference month {ref_label}", file=sys.stderr)

    # --- Country-level imports (current month) ---
    cur_rows = _census_get("imports", {
        "get": "GEN_VAL_MO,CTY_NAME,CTY_CODE",
        "YEAR": str(ref_y), "MONTH": f"{ref_m:02d}",
    })
    if not cur_rows:
        return {}

    hdr = cur_rows[0]
    try:
        vi, ni, ci = hdr.index("GEN_VAL_MO"), hdr.index("CTY_NAME"), hdr.index("CTY_CODE")
    except ValueError:
        return {}

    # Census returns one row per (country × commodity level) — aggregate per country
    cur_by_code: dict[str, dict[str, Any]] = {}
    for row in cur_rows[1:]:
        try:
            code, name, val = row[ci], row[ni], int(row[vi] or 0)
            if not code or not name or val <= 0:
                continue
            if code not in cur_by_code:
                cur_by_code[code] = {"country": name, "code": code, "val_k_usd": 0}
            cur_by_code[code]["val_k_usd"] += val
        except (ValueError, IndexError):
            continue

    if not cur_by_code:
        return {}

    # Previous year same month for YoY growth
    prev_rows = _census_get("imports", {
        "get": "GEN_VAL_MO,CTY_CODE",
        "YEAR": str(prev_y), "MONTH": f"{ref_m:02d}",
    })
    prev_by_code: dict[str, int] = {}
    if prev_rows and len(prev_rows) > 1:
        ph = prev_rows[0]
        try:
            pvi, pci = ph.index("GEN_VAL_MO"), ph.index("CTY_CODE")
            for row in prev_rows[1:]:
                code = row[pci]
                prev_by_code[code] = prev_by_code.get(code, 0) + int(row[pvi] or 0)
        except (ValueError, IndexError):
            pass

    # Attach YoY and sort by import value
    partners = list(cur_by_code.values())
    for p in partners:
        py = prev_by_code.get(p["code"], 0)
        p["yoy_pct"] = round((p["val_k_usd"] - py) / py * 100, 1) if py > 0 else None
    partners.sort(key=lambda x: x["val_k_usd"], reverse=True)

    # Fastest growing exporters to US (min $500M/month base to filter noise)
    min_base_k = 500_000
    fastest_growing = sorted(
        [p for p in partners if p.get("yoy_pct") is not None and p["val_k_usd"] >= min_base_k],
        key=lambda x: x["yoy_pct"], reverse=True,
    )[:10]

    result: dict[str, Any] = {
        "reference_month": ref_label,
        "top_import_partners": partners[:15],
        "fastest_growing_exporters_to_us": fastest_growing,
    }

    # --- End-use category imports (Foods/Industrial/Capital/Automotive/Consumer/Other) ---
    # Census end-use classification = the FT-900 press release breakdown.
    # Try two possible field-name conventions; fail silently if neither works.
    for desc_field in ("END_USE_SDESC", "I_COMMODITY_SDESC"):
        enduse_rows = _census_get("imports", {
            "get": f"GEN_VAL_MO,{desc_field}",
            "YEAR": str(ref_y), "MONTH": f"{ref_m:02d}",
            "CTY_CODE": "0000",
        })
        if not enduse_rows or len(enduse_rows) < 2:
            continue
        eh = enduse_rows[0]
        if desc_field not in eh:
            continue
        evi = eh.index("GEN_VAL_MO")
        edi = eh.index(desc_field)
        enduse_agg: dict[str, int] = {}
        for row in enduse_rows[1:]:
            try:
                desc, val = row[edi], int(row[evi] or 0)
                if desc:
                    enduse_agg[desc] = enduse_agg.get(desc, 0) + val
            except (ValueError, IndexError):
                continue
        if enduse_agg:
            enduse_list = sorted(
                [{"category": k, "val_k_usd": v} for k, v in enduse_agg.items()],
                key=lambda x: x["val_k_usd"], reverse=True,
            )
            result["enduse_imports"] = enduse_list
            break  # got it, no need to try other field name

    result["note"] = f"Census Bureau intltrade API. Values in thousands USD. Ref: {ref_label}."
    return result


def collect(target: date, force: bool = False) -> Path:
    out_path = ROOT / "data" / "raw" / f"{target.isoformat()}.json"
    history_path = ROOT / "data" / "fred_history.json"
    if out_path.exists() and not force:
        print(f"Already exists: {out_path} (use --force to overwrite)")
        return out_path

    print(f"Collecting US macro data for {target.isoformat()}...")
    print("  Scraping investing.com economic calendar...")
    releases = scrape_investing_calendar(target)
    print(f"  Found {len(releases)} US releases")

    # Deterministic enrichment: parse numbers, score surprise, tag groups.
    # Moves "hard logic" out of the LLM so any agent reading the JSON gets a
    # consistent analysis scaffold for free.
    from enrich_releases import enrich_releases
    release_summary = enrich_releases(releases)
    print(f"  Enriched: {release_summary['signal_release_count']} signal / "
          f"{release_summary['noise_release_count']} noise, "
          f"surprise_count={release_summary['surprise_count']}")

    print("  Fetching FRED snapshot...")
    if FRED_API_KEY:
        fred_trimmed, fred_full = fetch_fred_snapshot()
    else:
        fred_trimmed, fred_full = {}, {}
        print("  WARNING: FRED_API_KEY not set in .env — skipping FRED data")

    # Raw daily JSON: trimmed (latest + last 3 obs + pre-computed YoY/MoM/3mo).
    # ~9-12K tokens for LLM analyst vs ~42K for full version.
    from enrich_releases import (
        build_inflation_context,
        build_inflation_drivers,
        build_growth_context,
        build_cycle_context,
    )
    if fred_trimmed:
        inflation_context = build_inflation_context(fred_trimmed)
        # Sub-component attribution: which CPI groups pull inflation up vs down.
        inflation_context["drivers"] = build_inflation_drivers(fred_trimmed)
        # GDP engine attribution: locomotive vs drag (pp contributions).
        growth_context = build_growth_context(fred_trimmed)
        # Cycle gauge (Sahm + yield curve) — needs FULL history, not the 3-obs trim.
        cycle_context = build_cycle_context(fred_full)
    else:
        inflation_context = None
        growth_context = None
        cycle_context = None

    # Fetch Census trade detail only on trade release days (FT-900 monthly report).
    # Census API is free/no-key; data lags ~5 weeks so reference month = 2 months prior.
    trade_detail: dict[str, Any] = {}
    if "trade" in release_summary.get("groups_present", []):
        print("  Trade releases detected — fetching Census trade detail...")
        trade_detail = fetch_census_trade_detail(target)
        if trade_detail:
            n_partners = len(trade_detail.get("top_import_partners", []))
            n_growing = len(trade_detail.get("fastest_growing_exporters_to_us", []))
            has_enduse = "enduse_imports" in trade_detail
            print(f"  Census: {n_partners} partners, {n_growing} fastest growing, end-use={'yes' if has_enduse else 'no'}")
        else:
            print("  Census trade: unavailable (non-blocking)")

    # Today's net signed surprise (feeds the Economic Surprise Index time series).
    from enrich_releases import day_surprise_score
    release_summary["day_surprise_score"] = day_surprise_score(releases)

    payload = {
        "date": target.isoformat(),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "release_summary": release_summary,
        "inflation_context": inflation_context,
        "growth_context": growth_context,
        "cycle_context": cycle_context,
        "trade_detail": trade_detail,
        "releases": releases,
        "fred_snapshot": fred_trimmed,
        "sources": {
            "investing.com": True,
            "fred": bool(fred_trimmed),
            "census_trade": bool(trade_detail),
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"  Wrote {out_path}")

    # Separate full-history file — overwritten daily, used ONLY by dashboard charts,
    # NEVER read by LLM agents.
    if fred_full:
        history_payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "fred_snapshot": fred_full,
        }
        history_path.write_text(json.dumps(history_payload, indent=2, ensure_ascii=False))
        print(f"  Wrote {history_path}")

    return out_path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", help="YYYY-MM-DD (default: today NY time)")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    if args.date:
        target = date.fromisoformat(args.date)
    else:
        # Use New York date (UTC-5 in winter, UTC-4 in summer — close enough with UTC-5)
        ny_now = datetime.now(timezone.utc) - timedelta(hours=5)
        target = ny_now.date()

    collect(target, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
