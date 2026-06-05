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
OUT = ROOT / "data" / "sectors_latest.json"

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


def pct(a: float, b: float) -> float | None:
    if b in (0, None) or a is None:
        return None
    return round((a - b) / b * 100, 2)


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


def fetch_all(period: str = "2y") -> dict:
    tickers = list(SECTORS.keys()) + [BENCHMARK]
    print(f"Fetching {len(tickers)} tickers from Yahoo Finance...")
    data = yf.download(tickers, period=period, auto_adjust=True, progress=False, group_by="ticker")

    # Result: dict per ticker
    closes = {}
    for t in tickers:
        try:
            s = data[t]["Close"].dropna()
            if len(s) == 0:
                print(f"  WARNING: no data for {t}")
                continue
            closes[t] = s
        except Exception as exc:
            print(f"  WARNING: failed to extract {t}: {exc}")

    spy_closes = closes.get(BENCHMARK)
    if spy_closes is None:
        print("  ERROR: SPY benchmark missing — RS will not be computed")

    sectors_out = {}
    for ticker, name in SECTORS.items():
        s = closes.get(ticker)
        if s is None:
            continue
        info = compute_returns(s)
        info["name"] = name
        info["ticker"] = ticker

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

        sectors_out[ticker] = info

    benchmark_out = {}
    if spy_closes is not None:
        benchmark_out = compute_returns(spy_closes)
        benchmark_out["name"] = "S&P 500 (SPY benchmark)"
        benchmark_out["ticker"] = BENCHMARK

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": benchmark_out,
        "sectors": sectors_out,
    }


def main() -> int:
    payload = fetch_all()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Wrote {OUT}")
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
