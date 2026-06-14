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
    # Labor
    "PAYEMS": "Nonfarm Payrolls",
    "UNRATE": "Unemployment Rate",
    "ICSA": "Initial Jobless Claims",
    "CES0500000003": "Avg Hourly Earnings",
    "JTSJOL": "Job Openings (JOLTS)",
    # Growth
    # GDP: investing.com headline = QoQ annualized growth RATE (e.g. +1.6%), not the
    # level in $B. A191RL1Q225SBEA is already that rate → chart it directly (view=level).
    "A191RL1Q225SBEA": "Real GDP Growth (QoQ ann.)",
    # GDP components — level series (Chained 2017 $B, SAAR quarterly); mom_pct = QoQ%
    "PCECC96": "Real PCE (Chained 2017 $B)",
    "A006RL1Q225SBEA": "Real Gross Private Investment Growth QoQ ann.",
    "GCEC96": "Real Government Spending (Chained 2017 $B)",
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
    - trimmed: small snapshot for daily raw JSON (last 20 obs + pre-computed YoY/MoM/3mo)
    - full: full history for separate fred_history.json (overwrite daily)

    This dual output lets LLM analyst read a compact ~7K token raw JSON while the
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
        # Trimmed: last 20 observations (sufficient for analyst short-term context)
        trimmed[series_id] = {**common, "history": history[-20:]}
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

    # Raw daily JSON: trimmed (latest + last 20 obs + pre-computed YoY/MoM/3mo).
    # ~7K tokens for LLM analyst vs ~42K for full version.
    payload = {
        "date": target.isoformat(),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "release_summary": release_summary,
        "releases": releases,
        "fred_snapshot": fred_trimmed,
        "sources": {
            "investing.com": True,
            "fred": bool(fred_trimmed),
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
