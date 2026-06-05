#!/usr/bin/env python3
"""Fetch upcoming catalysts: earnings (top sector holdings) + macro releases (FRED).

Outputs data/calendar_latest.json with events in the next ~21 days:
{
  fetched_at,
  earnings: [{date, ticker, name, sector_etf, sector}, ...],
  macro: [{date, name, release_id}, ...]
}
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
import yfinance as yf
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OUT = ROOT / "data" / "calendar_latest.json"
FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()

# Top holdings per SPDR sector ETF (approximate, updated periodically).
# We track these for earnings — they move their sector ETF the most.
SECTOR_TOP_HOLDINGS = {
    "XLK": [("AAPL", "Apple"), ("MSFT", "Microsoft"), ("NVDA", "Nvidia"), ("AVGO", "Broadcom"), ("ORCL", "Oracle")],
    "XLF": [("BRK-B", "Berkshire B"), ("JPM", "JPMorgan"), ("V", "Visa"), ("MA", "Mastercard"), ("BAC", "Bank of America")],
    "XLE": [("XOM", "Exxon Mobil"), ("CVX", "Chevron"), ("COP", "ConocoPhillips"), ("EOG", "EOG Resources"), ("SLB", "Schlumberger")],
    "XLV": [("LLY", "Eli Lilly"), ("UNH", "UnitedHealth"), ("JNJ", "Johnson & Johnson"), ("ABBV", "AbbVie"), ("MRK", "Merck")],
    "XLY": [("AMZN", "Amazon"), ("TSLA", "Tesla"), ("HD", "Home Depot"), ("MCD", "McDonald's"), ("BKNG", "Booking")],
    "XLP": [("WMT", "Walmart"), ("COST", "Costco"), ("PG", "P&G"), ("KO", "Coca-Cola"), ("PEP", "PepsiCo")],
    "XLI": [("GE", "GE Aerospace"), ("CAT", "Caterpillar"), ("RTX", "RTX"), ("UBER", "Uber"), ("HON", "Honeywell")],
    "XLB": [("LIN", "Linde"), ("SHW", "Sherwin-Williams"), ("APD", "Air Products"), ("FCX", "Freeport-McMoRan"), ("ECL", "Ecolab")],
    "XLU": [("NEE", "NextEra"), ("SO", "Southern"), ("DUK", "Duke Energy"), ("CEG", "Constellation"), ("AEP", "American Electric")],
    "XLRE": [("PLD", "Prologis"), ("AMT", "American Tower"), ("EQIX", "Equinix"), ("WELL", "Welltower"), ("PSA", "Public Storage")],
    "XLC": [("META", "Meta"), ("GOOGL", "Alphabet A"), ("GOOG", "Alphabet C"), ("NFLX", "Netflix"), ("TMUS", "T-Mobile")],
}

# FRED Release IDs for the most market-moving series.
# Map release_id → friendly name. Source: https://api.stlouisfed.org/fred/releases
FRED_RELEASES = {
    10: "Consumer Price Index (CPI)",
    11: "Industrial Production & Capacity Utilization",
    17: "Producer Price Index (PPI)",
    21: "Personal Income & Outlays (PCE)",
    50: "Employment Situation (NFP, Unemployment)",
    53: "Job Openings & Labor Turnover (JOLTS)",
    25: "Retail Sales",
    101: "Real GDP",
    91: "Consumer Confidence (Conference Board)",
    192: "Michigan Consumer Sentiment",
    96: "Housing Starts",
    97: "Existing Home Sales",
    151: "S&P/Case-Shiller Home Price",
    100: "Initial Jobless Claims",
    326: "Durable Goods Orders",
    8: "Federal Open Market Committee (FOMC)",
}


# FOMC 2026 schedule (hardcoded — Fed publishes 1 year ahead)
FOMC_DATES_2026 = [
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-11-04", "2026-12-16",
]


def fetch_fred_release_dates(start: date, end: date) -> list[dict[str, Any]]:
    """Estimate upcoming FRED releases by extrapolating from recent past dates.

    FRED doesn't expose future schedules via API. We:
    1. Get last 6 release dates per indicator
    2. Compute median gap between them
    3. Project next release = last_date + median_gap
    4. Keep if within [start, end]
    """
    out = []

    # FOMC: use hardcoded calendar
    for d_str in FOMC_DATES_2026:
        if start.isoformat() <= d_str <= end.isoformat():
            out.append({"date": d_str, "name": "FOMC Meeting (Fed rate decision)", "release_id": 8, "type": "macro"})

    if not FRED_API_KEY:
        return out

    for release_id, label in FRED_RELEASES.items():
        if release_id == 8:
            continue  # FOMC handled via hardcode
        url = "https://api.stlouisfed.org/fred/release/dates"
        params = {
            "release_id": release_id,
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "include_release_dates_with_no_data": "false",
            "sort_order": "desc",
            "limit": 6,
        }
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code != 200:
                continue
            past_dates = [d["date"] for d in r.json().get("release_dates", []) if d.get("date")]
            if len(past_dates) < 2:
                continue
            # Compute gaps between consecutive past releases (descending order)
            d_objs = [date.fromisoformat(d) for d in past_dates]
            gaps = [(d_objs[i] - d_objs[i + 1]).days for i in range(len(d_objs) - 1)]
            if not gaps:
                continue
            gaps.sort()
            # Filter out tiny gaps (data revisions within same release cluster, e.g. GDP advance→2nd→final)
            real_gaps = [g for g in gaps if g >= 7]
            if not real_gaps:
                # No reliable cadence — skip
                continue
            median_gap = real_gaps[len(real_gaps) // 2]
            # Project next release date(s)
            last = d_objs[0]
            projected = last + timedelta(days=median_gap)
            # Add up to 3 future projections (e.g. weekly Jobless Claims gives 3 in 21d)
            for _ in range(3):
                if projected > end:
                    break
                if projected >= start:
                    out.append({
                        "date": projected.isoformat(),
                        "name": label,
                        "release_id": release_id,
                        "type": "macro",
                        "estimated": True,
                    })
                projected = projected + timedelta(days=median_gap)
        except Exception as exc:
            print(f"  FRED release {release_id} failed: {exc}", file=sys.stderr)
    return out


def fetch_earnings_dates(start: date, end: date) -> list[dict[str, Any]]:
    """For each tracked stock, get next earnings date (via yfinance) and filter."""
    out = []
    all_tickers = []
    for etf, holdings in SECTOR_TOP_HOLDINGS.items():
        for ticker, name in holdings:
            all_tickers.append((ticker, name, etf))

    print(f"  Fetching earnings dates for {len(all_tickers)} stocks...")
    for ticker, name, etf in all_tickers:
        try:
            t = yf.Ticker(ticker)
            # get_earnings_dates returns past + upcoming; we want future only
            try:
                ed = t.get_earnings_dates(limit=8)
            except Exception:
                ed = None
            if ed is None or len(ed) == 0:
                # Fallback: try calendar attribute
                try:
                    cal = t.calendar
                    if cal and "Earnings Date" in cal:
                        eds = cal["Earnings Date"]
                        if isinstance(eds, list) and len(eds) > 0:
                            edate = eds[0]
                            if hasattr(edate, "strftime"):
                                _add_earnings(out, edate, ticker, name, etf, start, end)
                except Exception:
                    pass
                continue
            for ts in ed.index:
                _add_earnings(out, ts, ticker, name, etf, start, end)
        except Exception as exc:
            print(f"    {ticker} failed: {exc}", file=sys.stderr)
    return out


def _add_earnings(out: list, ts, ticker, name, etf, start, end):
    """Add earnings entry if date is in window [start, end]."""
    try:
        d = ts.date() if hasattr(ts, "date") else ts
        if isinstance(d, datetime):
            d = d.date()
        if d < start or d > end:
            return
        out.append({
            "date": d.isoformat(),
            "ticker": ticker,
            "name": name,
            "sector_etf": etf,
            "type": "earnings",
        })
    except Exception:
        pass


def main() -> int:
    today = date.today()
    end = today + timedelta(days=21)
    print(f"Fetching catalysts {today} → {end}...")

    macro = fetch_fred_release_dates(today, end)
    print(f"  {len(macro)} macro releases scheduled")

    earnings = fetch_earnings_dates(today, end)
    # Deduplicate by (ticker, date)
    seen = set()
    earnings_unique = []
    for e in earnings:
        k = (e["ticker"], e["date"])
        if k in seen:
            continue
        seen.add(k)
        earnings_unique.append(e)
    earnings_unique.sort(key=lambda x: x["date"])
    print(f"  {len(earnings_unique)} earnings dates")

    macro.sort(key=lambda x: x["date"])

    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "window_start": today.isoformat(),
        "window_end": end.isoformat(),
        "macro": macro,
        "earnings": earnings_unique,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
