#!/usr/bin/env python3
"""Fetch cross-asset commodities/crypto from Yahoo Finance.

Adds Gold, Copper, BTC (which are not on FRED at daily resolution) to complement
the FRED cross-asset series (DXY, VIX, WTI, HY spread, IG spread, 10Y breakeven).

Output: data/cross_asset_latest.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "cross_asset_latest.json"

# Yahoo ticker → display label
ASSETS = {
    "GC=F": "Gold Futures",
    "HG=F": "Copper Futures",
    "BTC-USD": "Bitcoin (BTC-USD)",
}


def pct(a, b):
    if b in (0, None) or a is None:
        return None
    return round((a - b) / b * 100, 2)


def compute_returns(closes):
    if closes is None or len(closes) == 0:
        return {}
    latest = float(closes.iloc[-1])
    out = {"latest": round(latest, 2), "latest_date": closes.index[-1].strftime("%Y-%m-%d")}
    lookbacks = {"1d": 1, "1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252}
    for key, n in lookbacks.items():
        if len(closes) > n:
            out[f"ret_{key}"] = pct(latest, float(closes.iloc[-n - 1]))
    current_year = closes.index[-1].year
    year_data = closes[closes.index.year == current_year]
    if len(year_data) > 1:
        out["ret_ytd"] = pct(latest, float(year_data.iloc[0]))

    # Keep tail history for charting (last ~252 days)
    tail = closes.tail(252)
    out["history"] = [
        {"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 2)}
        for d, v in zip(tail.index, tail.values)
    ]
    return out


def main() -> int:
    print(f"Fetching {len(ASSETS)} cross-asset tickers from Yahoo...")
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "assets": {},
    }
    data = yf.download(list(ASSETS.keys()), period="2y", auto_adjust=True, progress=False, group_by="ticker")
    for ticker, label in ASSETS.items():
        try:
            s = data[ticker]["Close"].dropna()
            if len(s) == 0:
                print(f"  WARNING: no data for {ticker}")
                continue
            info = compute_returns(s)
            info["ticker"] = ticker
            info["label"] = label
            payload["assets"][ticker] = info
        except Exception as exc:
            print(f"  WARNING: {ticker} failed: {exc}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Wrote {OUT}")
    print(f"  {len(payload['assets'])} assets")
    for t, a in payload["assets"].items():
        print(f"    {t}: ${a.get('latest')} ({a.get('ret_1m')}% 1M)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
