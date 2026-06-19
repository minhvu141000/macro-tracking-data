#!/usr/bin/env python3
"""Fetch DỰ BÁO + kỳ vọng từ các Fed vùng (Cách B) — phần FRED không có.

Nguồn (tải file Excel công khai, không cần API key):
  - Philadelphia Fed — Survey of Professional Forecasters (SPF): dự báo median
    tăng trưởng GDP thực + lạm phát CPI của giới dự báo chuyên nghiệp.
  - Philadelphia Fed — ADS Business Conditions Index: điều kiện kinh doanh tần
    suất ngày (business-day).
  - New York Fed — r* (Holston-Laubach-Williams): ước lượng lãi suất tự nhiên.
  - New York Fed — Survey of Consumer Expectations (SCE): kỳ vọng lạm phát 1 năm
    của hộ gia đình.

Output: data/fed_forecasts_history.json — shape giống eia_history.json
        {schema_version, series: {ID: {label, latest, previous, change_pct,
         history:[{date,value}], source, unit}}}
build_dashboard._merge_extra_history() sẽ merge vào history để chart + stat-context.

    python scripts/fetch_fed_forecasts.py

Lưu ý: file SPF do SAS xuất có docProps/core.xml ngày sai định dạng ('T 2:31'
thiếu zero-pad giờ) → openpyxl crash; _safe_xlsx() vá lại trước khi đọc.
"""
from __future__ import annotations

import io
import json
import re
import ssl
import sys
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "fed_forecasts_history.json"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

PHILLY = "https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data"
NYFED = "https://www.newyorkfed.org/medialibrary"
URLS = {
    "spf_rgdp": f"{PHILLY}/survey-of-professional-forecasters/data-files/files/median_rgdp_growth.xlsx",
    "spf_cpi": f"{PHILLY}/survey-of-professional-forecasters/data-files/files/median_cpi_level.xlsx",
    "ads": f"{PHILLY}/ads/ads_index_most_current_vintage.xlsx",
    "rstar": f"{NYFED}/media/research/economists/williams/data/Holston_Laubach_Williams_current_estimates.xlsx",
    "sce": f"{NYFED}/interactives/sce/sce/downloads/data/frbny-sce-data.xlsx",
}


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=60, context=_CTX).read()


def _safe_xlsx(raw: bytes) -> io.BytesIO:
    """Repackage xlsx, sửa docProps/core.xml date 'T 2:31' → 'T02:31'."""
    import zipfile
    zin = zipfile.ZipFile(io.BytesIO(raw))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "docProps/core.xml":
                txt = data.decode("utf-8", "ignore")
                txt = re.sub(r"(T)\s(\d:)", r"\g<1>0\2", txt)
                data = txt.encode("utf-8")
            zout.writestr(item, data)
    buf.seek(0)
    return buf


def _read(key: str, **kwargs) -> pd.DataFrame:
    return pd.read_excel(_safe_xlsx(_download(URLS[key])), **kwargs)


def _q_to_date(year: int, q: int) -> str:
    return f"{int(year)}-{(int(q) - 1) * 3 + 1:02d}-01"


def _series(label: str, unit: str, source: str, hist: list[dict]) -> dict | None:
    hist = [h for h in hist if h["value"] is not None]
    if not hist:
        return None
    hist.sort(key=lambda h: h["date"])
    latest, prev = hist[-1], (hist[-2] if len(hist) > 1 else None)
    change = (round((latest["value"] - prev["value"]) / prev["value"] * 100, 3)
              if prev and prev["value"] not in (0, None) else None)
    return {"label": label, "unit": unit, "source": source,
            "latest": latest, "previous": prev, "change_pct": change, "history": hist}


# ---- parsers (mỗi cái trả về list[{date,value}], có giới hạn độ dài để data.js gọn) ----

def parse_spf_gdp() -> dict | None:
    df = _read("spf_rgdp")
    # DRGDP3..DRGDP6 = dự báo tăng trưởng 4 quý TỚI (annualized) → trung bình = forward growth
    cols = [c for c in ["DRGDP3", "DRGDP4", "DRGDP5", "DRGDP6"] if c in df.columns]
    hist = []
    for _, r in df.iterrows():
        vals = [r[c] for c in cols if pd.notna(r[c])]
        if not vals or pd.isna(r["YEAR"]) or pd.isna(r["QUARTER"]):
            continue
        hist.append({"date": _q_to_date(r["YEAR"], r["QUARTER"]),
                     "value": round(sum(vals) / len(vals), 3)})
    return _series("SPF: Dự báo tăng trưởng GDP (4 quý tới)", "% (annualized)",
                   "Philadelphia Fed — Survey of Professional Forecasters", hist[-80:])


def parse_spf_cpi() -> dict | None:
    df = _read("spf_cpi")
    # CPIB = dự báo lạm phát CPI trung bình NĂM TỚI (annual). Fallback CPIA (năm nay).
    col = "CPIB" if "CPIB" in df.columns else ("CPIA" if "CPIA" in df.columns else None)
    hist = []
    if col:
        for _, r in df.iterrows():
            if pd.isna(r[col]) or pd.isna(r["YEAR"]) or pd.isna(r["QUARTER"]):
                continue
            hist.append({"date": _q_to_date(r["YEAR"], r["QUARTER"]), "value": round(float(r[col]), 3)})
    return _series("SPF: Dự báo lạm phát CPI (năm tới)", "% YoY",
                   "Philadelphia Fed — Survey of Professional Forecasters", hist[-80:])


def parse_ads() -> dict | None:
    df = _read("ads")
    dcol, vcol = df.columns[0], df.columns[1]  # Date, ADS_Index
    hist = []
    for _, r in df.iterrows():
        d = str(r[dcol]).strip()
        m = re.match(r"(\d{4})\D(\d{2})\D(\d{2})", d)  # 1960:03:01
        if not m or pd.isna(r[vcol]):
            continue
        hist.append({"date": f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "value": round(float(r[vcol]), 4)})
    return _series("ADS: Điều kiện kinh doanh (Philly Fed)", "Index (0 = trung bình)",
                   "Philadelphia Fed — Aruoba-Diebold-Scotti", hist[-600:])


def parse_rstar() -> dict | None:
    df = _read("rstar", sheet_name="HLW Estimates", header=5)
    if "Date" not in df.columns or "US" not in df.columns:
        return None
    hist = []
    for _, r in df.iterrows():
        if pd.isna(r["Date"]) or pd.isna(r["US"]):
            continue
        d = pd.to_datetime(r["Date"]).strftime("%Y-%m-%d")
        hist.append({"date": d, "value": round(float(r["US"]), 3)})
    return _series("r* — Lãi suất tự nhiên (NY Fed, HLW · US)", "%",
                   "New York Fed — Holston-Laubach-Williams", hist[-80:])


def parse_sce() -> dict | None:
    df = _read("sce", sheet_name="Inflation expectations", header=3)
    dcol = df.columns[0]
    vcol = next((c for c in df.columns if str(c).startswith("Median one-year")), None)
    if vcol is None:
        return None
    hist = []
    for _, r in df.iterrows():
        ym = r[dcol]
        if pd.isna(ym) or pd.isna(r[vcol]):
            continue
        ym = str(int(ym))  # 202605
        if len(ym) != 6:
            continue
        hist.append({"date": f"{ym[:4]}-{ym[4:]}-01", "value": round(float(r[vcol]), 3)})
    return _series("SCE: Kỳ vọng lạm phát 1 năm (NY Fed)", "% (median hộ gia đình)",
                   "New York Fed — Survey of Consumer Expectations", hist[-120:])


PARSERS = {
    "SPF_GDP": parse_spf_gdp,
    "SPF_CPI": parse_spf_cpi,
    "ADS": parse_ads,
    "NYFED_RSTAR": parse_rstar,
    "SCE_INFL_1Y": parse_sce,
}


def main() -> int:
    series = {}
    for sid, fn in PARSERS.items():
        try:
            s = fn()
            if s:
                series[sid] = s
                print(f"  {sid}: {len(s['history'])} điểm, mới nhất "
                      f"{s['latest']['date']}={s['latest']['value']}")
            else:
                print(f"  {sid}: không có dữ liệu (skip)")
        except Exception as exc:
            print(f"  {sid}: LỖI {type(exc).__name__}: {str(exc)[:80]} (skip)")
    if not series:
        print("Không lấy được series nào — giữ file cũ nếu có.")
        return 0
    OUT.write_text(json.dumps({"schema_version": "1.0", "series": series},
                              indent=2, ensure_ascii=False))
    print(f"Wrote {OUT} ({len(series)} series)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
