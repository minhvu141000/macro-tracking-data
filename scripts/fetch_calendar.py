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

SCHEMA_VERSION = "1.1"  # bump when payload structure changes

# Expanded to top ~10 holdings per sector — total ~110 tickers for earnings coverage.
SECTOR_TOP_HOLDINGS = {
    "XLK": [("AAPL","Apple"),("MSFT","Microsoft"),("NVDA","Nvidia"),("AVGO","Broadcom"),("ORCL","Oracle"),
            ("CRM","Salesforce"),("AMD","AMD"),("ADBE","Adobe"),("ACN","Accenture"),("CSCO","Cisco"),
            ("INTU","Intuit"),("TXN","Texas Instruments")],
    "XLF": [("BRK-B","Berkshire B"),("JPM","JPMorgan"),("V","Visa"),("MA","Mastercard"),("BAC","Bank of America"),
            ("WFC","Wells Fargo"),("GS","Goldman Sachs"),("MS","Morgan Stanley"),("BLK","BlackRock"),("AXP","American Express"),
            ("C","Citigroup"),("SCHW","Charles Schwab")],
    "XLE": [("XOM","Exxon Mobil"),("CVX","Chevron"),("COP","ConocoPhillips"),("EOG","EOG Resources"),("SLB","Schlumberger"),
            ("MPC","Marathon Petroleum"),("PSX","Phillips 66"),("WMB","Williams Cos"),("OKE","ONEOK"),("VLO","Valero")],
    "XLV": [("LLY","Eli Lilly"),("UNH","UnitedHealth"),("JNJ","Johnson & Johnson"),("ABBV","AbbVie"),("MRK","Merck"),
            ("PFE","Pfizer"),("TMO","Thermo Fisher"),("ABT","Abbott"),("ISRG","Intuitive Surgical"),("AMGN","Amgen")],
    "XLY": [("AMZN","Amazon"),("TSLA","Tesla"),("HD","Home Depot"),("MCD","McDonald's"),("BKNG","Booking"),
            ("LOW","Lowe's"),("TJX","TJX"),("SBUX","Starbucks"),("NKE","Nike"),("ABNB","Airbnb")],
    "XLP": [("WMT","Walmart"),("COST","Costco"),("PG","P&G"),("KO","Coca-Cola"),("PEP","PepsiCo"),
            ("PM","Philip Morris"),("MO","Altria"),("MDLZ","Mondelez"),("CL","Colgate"),("TGT","Target")],
    "XLI": [("GE","GE Aerospace"),("CAT","Caterpillar"),("RTX","RTX"),("UBER","Uber"),("HON","Honeywell"),
            ("BA","Boeing"),("UNP","Union Pacific"),("DE","Deere"),("LMT","Lockheed Martin"),("ETN","Eaton")],
    "XLB": [("LIN","Linde"),("SHW","Sherwin-Williams"),("APD","Air Products"),("FCX","Freeport-McMoRan"),("ECL","Ecolab"),
            ("NEM","Newmont"),("DOW","Dow"),("DD","DuPont"),("PPG","PPG Industries"),("NUE","Nucor")],
    "XLU": [("NEE","NextEra"),("SO","Southern"),("DUK","Duke Energy"),("CEG","Constellation"),("AEP","American Electric"),
            ("SRE","Sempra"),("D","Dominion"),("PCG","PG&E"),("EXC","Exelon"),("XEL","Xcel Energy")],
    "XLRE": [("PLD","Prologis"),("AMT","American Tower"),("EQIX","Equinix"),("WELL","Welltower"),("PSA","Public Storage"),
             ("DLR","Digital Realty"),("O","Realty Income"),("SPG","Simon Property"),("CCI","Crown Castle"),("VICI","VICI Properties")],
    "XLC": [("META","Meta"),("GOOGL","Alphabet A"),("GOOG","Alphabet C"),("NFLX","Netflix"),("DIS","Disney"),
            ("TMUS","T-Mobile"),("VZ","Verizon"),("T","AT&T"),("CMCSA","Comcast"),("EA","Electronic Arts")],
}

# Tickers considered HIGH importance (S&P 500 weight > 1.5% OR market-moving)
HIGH_IMPORTANCE_TICKERS = {
    "AAPL", "MSFT", "NVDA", "AVGO", "GOOGL", "GOOG", "META", "AMZN", "TSLA",
    "BRK-B", "JPM", "LLY", "UNH", "XOM", "ORCL", "WMT", "COST", "V", "MA",
    "NFLX", "HD", "CRM", "AMD", "ABBV", "PG", "JNJ", "WFC", "BAC", "DIS", "BA",
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


# Fed speaker impact mapping. Powell = highest market mover; vice chairs + governors = high;
# regional Fed presidents = medium; non-voting regional = low.
FED_SPEAKER_IMPACT = {
    # Chair + Vice chair
    "powell": "high", "jefferson": "high", "barr": "high",
    # Governors (voting members)
    "waller": "high", "bowman": "high", "kugler": "high", "cook": "high",
    # NY Fed president (permanent voter)
    "williams": "high",
    # Regional Fed presidents (rotating voters)
    "daly": "medium", "barkin": "medium", "kashkari": "medium",
    "logan": "medium", "goolsbee": "medium", "harker": "medium",
    "schmid": "medium", "musalem": "medium", "hammack": "medium",
    "collins": "medium", "bostic": "medium", "mester": "medium",
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


def _classify_time(ts) -> str:
    """Return 'BMO' (before market open), 'AMC' (after market close), or 'TBD'.

    Convention: yfinance earnings date is set to scheduled timestamp. We classify
    by hour in ET:
    - hour < 9 → BMO
    - hour >= 16 → AMC
    - else TBD (intraday rare; typically yfinance gives midnight when unknown)
    """
    try:
        if not hasattr(ts, "hour"):
            return "TBD"
        h = ts.hour
        if h == 0:
            return "TBD"
        if h < 9:
            return "BMO"
        if h >= 16:
            return "AMC"
        return "TBD"
    except Exception:
        return "TBD"


def fetch_earnings_dates(start: date, end: date) -> list[dict[str, Any]]:
    """For each tracked stock, get next earnings date + EPS/revenue estimates.

    Pulls per-ticker:
    - eps_estimate (analyst consensus)
    - revenue_estimate_b (in $B)
    - time: BMO / AMC / TBD
    - importance: high / medium (based on HIGH_IMPORTANCE_TICKERS)
    """
    out = []
    all_tickers = []
    for etf, holdings in SECTOR_TOP_HOLDINGS.items():
        for ticker, name in holdings:
            all_tickers.append((ticker, name, etf))

    print(f"  Fetching earnings + estimates for {len(all_tickers)} stocks...")
    for ticker, name, etf in all_tickers:
        try:
            t = yf.Ticker(ticker)
            ed = None
            try:
                ed = t.get_earnings_dates(limit=8)
            except Exception:
                ed = None

            if ed is None or len(ed) == 0:
                # Fallback to calendar attr
                try:
                    cal = t.calendar
                    if cal and "Earnings Date" in cal:
                        eds = cal["Earnings Date"]
                        if isinstance(eds, list) and len(eds) > 0:
                            edate = eds[0]
                            if hasattr(edate, "strftime"):
                                _add_earnings(out, edate, ticker, name, etf, start, end, None, None, None)
                except Exception:
                    pass
                continue

            # Extract EPS estimate + revenue estimate from earnings DataFrame
            for ts in ed.index:
                eps_est = None
                rev_est_b = None
                try:
                    row = ed.loc[ts]
                    # Column names vary; try common ones
                    for c in ["EPS Estimate", "epsEstimate", "estimate"]:
                        if c in row and row[c] is not None and not _is_nan(row[c]):
                            eps_est = round(float(row[c]), 3)
                            break
                except Exception:
                    pass

                # Get revenue estimate from analyst expectations
                if rev_est_b is None:
                    try:
                        info = t.info
                        re_avg = info.get("revenueAverage") or info.get("revenueEstimate")
                        if re_avg:
                            rev_est_b = round(float(re_avg) / 1e9, 2)
                    except Exception:
                        pass

                _add_earnings(out, ts, ticker, name, etf, start, end, eps_est, rev_est_b, _classify_time(ts))
        except Exception as exc:
            print(f"    {ticker} failed: {exc}", file=sys.stderr)
    return out


def scrape_upcoming_fed_speakers(start: date, end: date) -> list[dict[str, Any]]:
    """Scrape federalreserve.gov calendar for upcoming speaker events.

    Source: https://www.federalreserve.gov/newsevents/calendar.htm
    Renders client-side from JSON; use the underlying feed if available, else fallback.
    """
    out = []
    import re
    try:
        import requests
        url = "https://www.federalreserve.gov/json/ne-speech.json"
        r = requests.get(url, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0 (Macintosh) Chrome/120 Safari/537.36"})
        if r.status_code != 200:
            return out
        data = r.json()
        for item in data if isinstance(data, list) else []:
            # Example fields: d (date), t (title), l (location), s (speaker), time
            d_str = item.get("d") or item.get("date") or ""
            try:
                # Date format: "MM/DD/YYYY" or "YYYY-MM-DD"
                if "/" in d_str:
                    parts = d_str.split("/")
                    rel_date = date(int(parts[2]), int(parts[0]), int(parts[1]))
                else:
                    rel_date = date.fromisoformat(d_str[:10])
            except Exception:
                continue
            if rel_date < start or rel_date > end:
                continue
            speaker_full = (item.get("s") or item.get("speaker") or "").strip()
            # Extract last name (lowercased) for impact lookup
            speaker_last = (speaker_full.split()[-1] if speaker_full else "").lower()
            impact = FED_SPEAKER_IMPACT.get(speaker_last, "low")
            out.append({
                "date": rel_date.isoformat(),
                "time": item.get("time") or "—",
                "speaker": speaker_full or speaker_last.title(),
                "topic": item.get("t") or item.get("title") or "Speech",
                "venue": item.get("l") or item.get("location") or "",
                "impact": impact,
                "source": "federalreserve.gov",
            })
    except Exception as exc:
        print(f"  Fed scrape failed: {exc}", file=sys.stderr)
    return out


def extract_fed_speakers(start: date, end: date) -> list[dict[str, Any]]:
    """Build fed_speakers list combining:
    1. Upcoming events scraped from federalreserve.gov (forward-looking)
    2. Past events extracted from raw release files (backward-looking, contextual)
    Both restricted to [start, end] window.
    """
    out = scrape_upcoming_fed_speakers(start, end)
    seen_keys = {(s["date"], s["speaker"].lower()) for s in out}

    raw_dir = ROOT / "data" / "raw"
    if not raw_dir.exists():
        out.sort(key=lambda x: (x["date"], x.get("time", "")))
        return out

    import re
    for f in sorted(raw_dir.glob("*.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        rel_date_str = d.get("date") or f.stem
        try:
            rel_date = date.fromisoformat(rel_date_str)
        except Exception:
            continue
        if rel_date < start or rel_date > end:
            continue
        for r in d.get("releases", []):
            name = (r.get("name") or "").strip()
            if "speaks" not in name.lower():
                continue
            m = re.search(
                r"(?:fomc member|fed (?:chair|governor|vice chair[^ ]*)|fed)\s+([A-Z][a-z]+)\s+speaks",
                name, re.IGNORECASE)
            speaker = (m.group(1) if m else "Unknown").lower()
            key = (rel_date.isoformat(), speaker)
            if key in seen_keys:
                continue
            impact = FED_SPEAKER_IMPACT.get(speaker, "low")
            time_str = (r.get("time") or "")
            tm = re.search(r"(\d{2}:\d{2})", time_str)
            out.append({
                "date": rel_date.isoformat(),
                "time": tm.group(1) if tm else "—",
                "speaker": speaker.title(),
                "topic": name,
                "venue": "",
                "impact": impact,
                "source": "investing.com (historical)",
                "event_url": r.get("event_url"),
            })
            seen_keys.add(key)
    out.sort(key=lambda x: (x["date"], x.get("time", "")))
    return out


def _is_nan(x) -> bool:
    try:
        return x != x  # NaN test
    except Exception:
        return False


def _add_earnings(out: list, ts, ticker, name, etf, start, end,
                  eps_est=None, rev_est_b=None, time_class="TBD"):
    """Add earnings entry if date is in window [start, end]."""
    try:
        d = ts.date() if hasattr(ts, "date") else ts
        if isinstance(d, datetime):
            d = d.date()
        if d < start or d > end:
            return
        importance = "high" if ticker in HIGH_IMPORTANCE_TICKERS else "medium"
        out.append({
            "date": d.isoformat(),
            "ticker": ticker,
            "name": name,
            "sector_etf": etf,
            "time": time_class,
            "eps_estimate": eps_est,
            "revenue_estimate_b": rev_est_b,
            "importance": importance,
            "type": "earnings",
        })
    except Exception:
        pass


def build_lookahead(macro: list[dict], earnings: list[dict], fed_speakers: list[dict],
                     today: date) -> dict[str, Any]:
    """Deterministic 'what's next' slices: tomorrow + rest of this week.

    Filters earnings/Fed speakers to importance that matters for a macro report
    (high-importance tickers, high/medium Fed impact) so the analyst doesn't have
    to judge significance — only macro releases are kept unfiltered (all matter).
    """
    tomorrow = today + timedelta(days=1)
    week_end = today + timedelta(days=7)

    def _on(events: list[dict], d: date) -> list[dict]:
        return [e for e in events if e.get("date") == d.isoformat()]

    def _between(events: list[dict], start: date, end: date) -> list[dict]:
        return [e for e in events if start.isoformat() <= e.get("date", "") <= end.isoformat()]

    tomorrow_earnings = [e for e in _on(earnings, tomorrow) if e.get("importance") == "high"]
    tomorrow_fed = [e for e in _on(fed_speakers, tomorrow) if e.get("impact") in ("high", "medium")]

    week_earnings = [e for e in _between(earnings, today, week_end) if e.get("importance") == "high"]
    week_fed = [e for e in _between(fed_speakers, today, week_end) if e.get("impact") in ("high", "medium")]

    return {
        "tomorrow_date": tomorrow.isoformat(),
        "week_end_date": week_end.isoformat(),
        "tomorrow": {
            "macro": _on(macro, tomorrow),
            "earnings": tomorrow_earnings,
            "fed_speakers": tomorrow_fed,
        },
        "this_week": {
            "macro": _between(macro, today, week_end),
            "earnings": week_earnings,
            "fed_speakers": week_fed,
        },
    }


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

    fed_speakers = extract_fed_speakers(today, end)
    print(f"  {len(fed_speakers)} Fed speaker events (in raw history)")

    macro.sort(key=lambda x: x["date"])

    lookahead = build_lookahead(macro, earnings_unique, fed_speakers, today)
    print(f"  Lookahead: {len(lookahead['tomorrow']['macro'])} macro + "
          f"{len(lookahead['tomorrow']['earnings'])} earnings ngày mai; "
          f"{len(lookahead['this_week']['macro'])} macro + "
          f"{len(lookahead['this_week']['earnings'])} earnings tuần này")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "window_start": today.isoformat(),
        "window_end": end.isoformat(),
        "macro": macro,
        "earnings": earnings_unique,
        "fed_speakers": fed_speakers,
        "lookahead": lookahead,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
