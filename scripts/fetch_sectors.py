#!/usr/bin/env python3
"""Fetch 11 GICS sector ETFs (SPDR Select Sector) + SPY benchmark from Yahoo Finance.

Computes per-sector:
- Latest close + 1D/1W/1M/3M/6M/YTD/1Y returns
- Relative Strength (RS) vs SPY: cumulative price ratio normalized to 100
- 50-day vs 200-day MA cross signal

Output: data/sectors_latest.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sectors_latest.json"        # full (with rs_history) — for dashboard charts
OUT_LITE = ROOT / "data" / "sectors_lite.json"     # no rs_history — for LLM agents (~10x smaller)
OUT_HOLDINGS = ROOT / "data" / "sector_holdings_latest.json"  # per-stock universe — rotation handoff

SCHEMA_VERSION = "1.1"  # bump when payload structure changes

# 11 GICS Sectors via SPDR Select Sector ETFs + SPY benchmark
SECTORS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Healthcare",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLI": "Industrials",
    "XLB": "Materials",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
}
BENCHMARK = "SPY"

# Top ~12 holdings per sector ETF (cover bulk of weight) for breadth computation.
# These should represent ≥50% of each ETF's weight so breadth signal is meaningful.
SECTOR_BREADTH_HOLDINGS = {
    "XLK": ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "ADBE", "ACN", "CSCO", "INTU", "TXN"],
    "XLF": ["BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "BLK", "AXP", "C", "SCHW"],
    "XLE": ["XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "WMB", "OKE", "VLO", "OXY", "KMI"],
    "XLV": ["LLY", "UNH", "JNJ", "ABBV", "MRK", "PFE", "TMO", "ABT", "ISRG", "AMGN", "DHR", "BMY"],
    "XLY": ["AMZN", "TSLA", "HD", "MCD", "BKNG", "LOW", "TJX", "SBUX", "NKE", "ABNB", "MAR", "GM"],
    "XLP": ["WMT", "COST", "PG", "KO", "PEP", "PM", "MO", "MDLZ", "CL", "TGT", "KMB", "MNST"],
    "XLI": ["GE", "CAT", "RTX", "UBER", "HON", "BA", "UNP", "DE", "LMT", "ETN", "ADP", "WM"],
    "XLB": ["LIN", "SHW", "APD", "FCX", "ECL", "NEM", "DOW", "DD", "PPG", "NUE", "VMC", "MLM"],
    "XLU": ["NEE", "SO", "DUK", "CEG", "AEP", "SRE", "D", "PCG", "EXC", "XEL", "ED", "WEC"],
    "XLRE": ["PLD", "AMT", "EQIX", "WELL", "PSA", "DLR", "O", "SPG", "CCI", "CBRE", "VICI", "EXR"],
    "XLC": ["META", "GOOGL", "GOOG", "NFLX", "DIS", "TMUS", "VZ", "T", "CMCSA", "EA", "WBD", "CHTR"],
}


def pct(a: float, b: float) -> float | None:
    if b in (0, None) or a is None:
        return None
    return round((a - b) / b * 100, 2)


def compute_weekly_mf(closes, highs, lows, volumes) -> dict:
    """Compute volume-weighted Money Flow Index (MFI) over 5 and 14 trading days.

    MFI = positive_money_flow / total_money_flow × 100
    positive day: typical_price > prev_typical_price

    Returns flow_signal: STRONG_INFLOW (≥65) / INFLOW (55-65) / NEUTRAL (45-55)
                         / OUTFLOW (35-45) / STRONG_OUTFLOW (<35)
    """
    try:
        n = min(len(closes), len(highs), len(lows), len(volumes))
        if n < 6:
            return {}
        cl = closes.iloc[-n:]
        hi = highs.iloc[-n:]
        lo = lows.iloc[-n:]
        vo = volumes.iloc[-n:]
        typical = (hi + lo + cl) / 3
        raw_flow = typical * vo

        def _mfi(window: int) -> float | None:
            pos = neg = 0.0
            start = max(1, n - window)
            for i in range(start, n):
                if float(typical.iloc[i]) > float(typical.iloc[i - 1]):
                    pos += float(raw_flow.iloc[i])
                elif float(typical.iloc[i]) < float(typical.iloc[i - 1]):
                    neg += float(raw_flow.iloc[i])
            total = pos + neg
            return round(pos / total * 100, 1) if total > 0 else None

        mfi_5 = _mfi(5)
        mfi_14 = _mfi(14)
        out: dict = {}
        if mfi_5 is not None:
            out["mfi_5d"] = mfi_5
        if mfi_14 is not None:
            out["mfi_14d"] = mfi_14

        # Dollar volume participation (5-day, in billions)
        dv = float((typical.tail(5) * vo.tail(5)).sum())
        if dv > 0:
            out["dollar_vol_5d_bn"] = round(dv / 1e9, 2)

        # Signal label
        if mfi_5 is not None:
            if mfi_5 >= 65:
                out["flow_signal"] = "STRONG_INFLOW"
            elif mfi_5 >= 55:
                out["flow_signal"] = "INFLOW"
            elif mfi_5 >= 45:
                out["flow_signal"] = "NEUTRAL"
            elif mfi_5 >= 35:
                out["flow_signal"] = "OUTFLOW"
            else:
                out["flow_signal"] = "STRONG_OUTFLOW"
        return out
    except Exception:
        return {}


def compute_returns(closes) -> dict:
    """Given a pandas Series of closes (Date index, ascending), compute period returns."""
    if closes is None or len(closes) == 0:
        return {}
    latest = float(closes.iloc[-1])
    out = {"latest": round(latest, 2), "latest_date": closes.index[-1].strftime("%Y-%m-%d")}

    lookbacks = {"1d": 1, "1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252}
    for key, n in lookbacks.items():
        if len(closes) > n:
            out[f"ret_{key}"] = pct(latest, float(closes.iloc[-n - 1]))

    # YTD
    current_year = closes.index[-1].year
    year_data = closes[closes.index.year == current_year]
    if len(year_data) > 1:
        out["ret_ytd"] = pct(latest, float(year_data.iloc[0]))

    # 50/200-day SMA cross
    if len(closes) >= 200:
        ma50 = float(closes.tail(50).mean())
        ma200 = float(closes.tail(200).mean())
        out["ma50"] = round(ma50, 2)
        out["ma200"] = round(ma200, 2)
        out["above_ma50"] = latest > ma50
        out["above_ma200"] = latest > ma200
        out["golden_cross"] = ma50 > ma200  # bullish if true
    return out


def _pct_above_ma50_at(holdings_closes: dict, holdings: list, back: int) -> float | None:
    """% of holdings whose close was above its trailing MA50 `back` sessions ago.
    back=0 → today. Used to compute a self-contained breadth thrust (no persistence).
    """
    n_total = n_above = 0
    for h in holdings:
        s = holdings_closes.get(h)
        if s is None or len(s) < 50 + back + 1:
            continue
        end = len(s) - back
        latest = float(s.iloc[end - 1])
        ma50 = float(s.iloc[end - 50:end].mean())
        n_total += 1
        if latest > ma50:
            n_above += 1
    return round(n_above / n_total * 100, 1) if n_total else None


def compute_sector_breadth(sector_etf: str, holdings_closes: dict) -> dict:
    """Compute % of sector ETF's holdings above MA50 and MA200, plus breadth flag
    and a 5-session breadth THRUST (Δ pct_above_ma50) — the rotation-flow signal:
    money entering a sector lifts its members above MA50 before the cap-weighted
    ETF return shows it.

    Returns dict with:
    - pct_above_ma50, pct_above_ma200
    - breadth_flag: 'broad' (>65% above MA50), 'healthy' (40-65%), 'narrow' (<40%)
    - breadth_thrust: pct_above_ma50 now minus 5 sessions ago (signed pp)
    - holdings_checked: count of holdings successfully evaluated
    """
    holdings = SECTOR_BREADTH_HOLDINGS.get(sector_etf, [])
    if not holdings:
        return {}
    n_total = 0
    n_above_ma50 = 0
    n_above_ma200 = 0
    for h in holdings:
        s = holdings_closes.get(h)
        if s is None or len(s) < 200:
            continue
        latest = float(s.iloc[-1])
        ma50 = float(s.tail(50).mean())
        ma200 = float(s.tail(200).mean())
        n_total += 1
        if latest > ma50:
            n_above_ma50 += 1
        if latest > ma200:
            n_above_ma200 += 1
    if n_total == 0:
        return {}
    pct50 = round(n_above_ma50 / n_total * 100, 1)
    pct200 = round(n_above_ma200 / n_total * 100, 1)
    # Thresholds per Tactical Agent spec: <40 narrow, 40-65 healthy, >65 broad
    if pct50 > 65:
        flag = "broad"
    elif pct50 >= 40:
        flag = "healthy"
    else:
        flag = "narrow"
    out = {
        "pct_above_ma50": pct50,
        "pct_above_ma200": pct200,
        "breadth_flag": flag,
        "holdings_checked": n_total,
        "holdings_above_ma50": n_above_ma50,
        "holdings_above_ma200": n_above_ma200,
    }
    pct50_5d = _pct_above_ma50_at(holdings_closes, holdings, back=5)
    if pct50_5d is not None:
        out["breadth_thrust"] = round(pct50 - pct50_5d, 1)
    return out


def compute_holding_metrics(s, spy_closes) -> dict | None:
    """Per-stock snapshot for the rotation handoff universe: enough for a
    stock-picking agent to rank names within a sector without re-downloading.
    """
    if s is None or len(s) < 200:
        return None
    latest = float(s.iloc[-1])
    ma50 = float(s.tail(50).mean())
    ma200 = float(s.tail(200).mean())
    out = {
        "latest": round(latest, 2),
        "ret_1m": pct(latest, float(s.iloc[-22])) if len(s) > 22 else None,
        "ret_3m": pct(latest, float(s.iloc[-64])) if len(s) > 64 else None,
        "above_ma50": latest > ma50,
        "above_ma200": latest > ma200,
    }
    # Relative strength vs SPY = excess return (simple, good enough to rank names).
    if spy_closes is not None and len(spy_closes) > 22:
        spy_1m = pct(float(spy_closes.iloc[-1]), float(spy_closes.iloc[-22]))
        if out["ret_1m"] is not None and spy_1m is not None:
            out["rs_1m"] = round(out["ret_1m"] - spy_1m, 2)
    return out


def fetch_all(period: str = "2y") -> dict:
    # Build complete ticker list: sectors + benchmark + all unique breadth holdings
    breadth_tickers = sorted({h for hs in SECTOR_BREADTH_HOLDINGS.values() for h in hs})
    tickers = list(SECTORS.keys()) + [BENCHMARK] + breadth_tickers
    print(f"Fetching {len(tickers)} tickers from Yahoo Finance "
          f"({len(SECTORS)} sectors + {len(breadth_tickers)} holdings for breadth)...")
    data = yf.download(tickers, period=period, auto_adjust=True, progress=False, group_by="ticker")

    # Result: dict per ticker (close + OHLV for sector ETFs + benchmark)
    closes = {}
    highs: dict = {}
    lows: dict = {}
    volumes: dict = {}
    sector_and_bench = list(SECTORS.keys()) + [BENCHMARK]
    for t in tickers:
        try:
            s = data[t]["Close"].dropna()
            if len(s) == 0:
                continue
            closes[t] = s
            if t in sector_and_bench:
                highs[t] = data[t]["High"].dropna()
                lows[t] = data[t]["Low"].dropna()
                volumes[t] = data[t]["Volume"].dropna()
        except Exception:
            pass

    spy_closes = closes.get(BENCHMARK)
    if spy_closes is None:
        print("  ERROR: SPY benchmark missing — RS will not be computed")

    # Compute SPY money flow baseline (used for relative MFI)
    spy_mf = compute_weekly_mf(
        spy_closes,
        highs.get(BENCHMARK),
        lows.get(BENCHMARK),
        volumes.get(BENCHMARK),
    ) if spy_closes is not None else {}
    spy_mfi_5 = spy_mf.get("mfi_5d")

    sectors_out = {}
    for ticker, name in SECTORS.items():
        s = closes.get(ticker)
        if s is None:
            continue
        info = compute_returns(s)
        info["name"] = name
        info["ticker"] = ticker

        # Compute breadth from individual holdings
        breadth = compute_sector_breadth(ticker, closes)
        if breadth:
            info["breadth"] = breadth

        # Relative Strength vs SPY: rolling ratio normalized to 100 at the start
        if spy_closes is not None:
            # Align indices
            aligned = s.align(spy_closes, join="inner")
            ratio = (aligned[0] / aligned[1])
            if len(ratio) > 0:
                ratio_norm = (ratio / ratio.iloc[0]) * 100
                # Sample to last ~252 days (1y) for chart, daily resolution
                tail = ratio_norm.tail(252)
                info["rs_history"] = [
                    {"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 2)}
                    for d, v in zip(tail.index, tail.values)
                ]
                # RS performance vs SPY for each window
                for key, n in [("1w", 5), ("1m", 21), ("3m", 63), ("6m", 126), ("1y", 252)]:
                    if len(ratio_norm) > n:
                        info[f"rs_{key}"] = pct(float(ratio_norm.iloc[-1]), float(ratio_norm.iloc[-n - 1]))
                if len(ratio_norm) > 1:
                    cy = ratio_norm[ratio_norm.index.year == ratio_norm.index[-1].year]
                    if len(cy) > 1:
                        info["rs_ytd"] = pct(float(cy.iloc[-1]), float(cy.iloc[0]))
                # RS slope (momentum of relative strength): is the last week of RS
                # outpacing the monthly run-rate? >0 = RS accelerating = rotation IN.
                if info.get("rs_1w") is not None and info.get("rs_1m") is not None:
                    info["rs_slope"] = round(info["rs_1w"] - info["rs_1m"] * (5 / 21), 2)

        # Volume-based money flow (ETF level)
        mf = compute_weekly_mf(
            s, highs.get(ticker), lows.get(ticker), volumes.get(ticker)
        )
        if mf:
            # Relative MFI vs SPY: positive = sector getting more inflow than market
            if "mfi_5d" in mf and spy_mfi_5 is not None:
                mf["mfi_vs_spy"] = round(mf["mfi_5d"] - spy_mfi_5, 1)
            info["money_flow"] = mf

        sectors_out[ticker] = info

    benchmark_out = {}
    if spy_closes is not None:
        benchmark_out = compute_returns(spy_closes)
        benchmark_out["name"] = "S&P 500 (SPY benchmark)"
        benchmark_out["ticker"] = BENCHMARK

    # Per-stock universe per sector — the candidate list a stock-picking agent
    # filters once the rotation engine flags a sector. Data already downloaded.
    holdings_out = {}
    for ticker in SECTORS:
        members = []
        for h in SECTOR_BREADTH_HOLDINGS.get(ticker, []):
            m = compute_holding_metrics(closes.get(h), spy_closes)
            if m:
                m["ticker"] = h
                members.append(m)
        members.sort(key=lambda x: (x.get("rs_1m") is not None, x.get("rs_1m", -999)), reverse=True)
        if members:
            holdings_out[ticker] = members

    return {
        "schema_version": SCHEMA_VERSION,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": benchmark_out,
        "sectors": sectors_out,
        "holdings": holdings_out,
    }


def make_lite(payload: dict) -> dict:
    """Strip the large rs_history array from each sector — agents only read the
    scalar metrics (ret_*, rs_*, above_ma200, breadth). Cuts the file ~10x
    (~56K → ~5K tokens) while preserving every signal the agents actually use.
    """
    lite = {k: v for k, v in payload.items() if k not in ("sectors", "holdings")}
    lite["sectors"] = {}
    for ticker, info in payload.get("sectors", {}).items():
        lite["sectors"][ticker] = {k: v for k, v in info.items() if k != "rs_history"}
    return lite


def main() -> int:
    payload = fetch_all()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Holdings universe → its own file (rotation handoff); keep it out of the
    # dashboard/agent sector files which only need ETF-level metrics.
    holdings = payload.pop("holdings", {})
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    OUT_LITE.write_text(json.dumps(make_lite(payload), indent=2, ensure_ascii=False))
    OUT_HOLDINGS.write_text(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "fetched_at": payload["fetched_at"],
        "note": "Candidate universe per sector for the stock-picking agent. "
                "Sorted by rs_1m (excess return vs SPY). Filtered downstream once "
                "build_sector_rotation.py flags a sector.",
        "holdings": holdings,
    }, indent=2, ensure_ascii=False))
    print(f"Wrote {OUT}")
    print(f"Wrote {OUT_LITE} (no rs_history — for agents)")
    print(f"Wrote {OUT_HOLDINGS} ({sum(len(v) for v in holdings.values())} stocks across {len(holdings)} sectors)")
    print(f"  {len(payload['sectors'])} sectors collected")
    # Print quick leaderboard 1M return
    leaders = sorted(
        payload["sectors"].values(),
        key=lambda x: x.get("ret_1m", -999),
        reverse=True,
    )
    print("\n  1-month leaders:")
    for s in leaders[:5]:
        rs = s.get("rs_1m")
        rs_txt = f" (RS {rs:+.1f}%)" if rs is not None else ""
        ret = s.get("ret_1m")
        ret_txt = f"{ret:+.2f}%" if ret is not None else "n/a"
        print(f"    {s['ticker']} {s['name']}: {ret_txt}{rs_txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
