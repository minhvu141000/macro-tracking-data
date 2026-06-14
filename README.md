# Vĩ mô Mỹ — Tracking System

Hệ thống agent thu thập, phân tích và visualize chỉ số vĩ mô Mỹ hàng ngày.

## Quick start

### 1. Lấy FRED API key (miễn phí, ~2 phút)

1. Vào https://fred.stlouisfed.org/docs/api/api_key.html
2. Bấm "Request API Key" — đăng ký tài khoản St. Louis Fed (email + password).
3. Sau khi xác nhận email, vào https://fredaccount.stlouisfed.org/apikeys → "Request API Key".
4. Mô tả use case: "Personal use — tracking US macro indicators for investment research"
5. Copy key (32 ký tự).

### 2. Cấu hình

```bash
cd "Vĩ mô Mỹ Tracking"
cp .env.example .env
# Mở .env, paste FRED_API_KEY=<key của bạn>
```

### 3. Cài Python deps

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium   # ~92MB Chromium cho scraper
```

### 4. Test thử

```bash
# Thu thập data cho 1 ngày cụ thể
python scripts/collect.py --date 2026-05-21

# Build dashboard
python scripts/build_dashboard.py

# Mở dashboard
open dashboard/index.html
```

## Hàng ngày

Trong Claude Code, chạy:
```
/daily-macro
```

Hoặc cho 1 ngày cụ thể:
```
/daily-macro 2026-05-21
```

Quy trình tự động:
1. `macro-collector` scrape investing.com + gọi FRED API
2. `macro-analyst` viết báo cáo phân tích vào `data/daily/<date>.md`
3. `macro-trend` cập nhật trend signals
4. `macro-dashboard` rebuild `dashboard/data.js`

Mở `dashboard/index.html` để xem.

## Cuối tháng

```
/monthly-macro 2026-05
```

Sinh báo cáo `data/monthly/2026-05.md` với:
- Đánh giá regime (expansion/slowdown/recession/recovery/stagflation)
- Fed stance (hawkish/neutral/dovish)
- Sector winners/losers theo 11 GICS
- Top 3 conviction calls
- Risks & catalysts tháng tới

## Cấu trúc

```
.claude/
  agents/                 # 4 sub-agent: collector, analyst, trend, dashboard
  commands/               # /daily-macro, /monthly-macro
scripts/
  collect.py              # scraper + FRED client
  build_dashboard.py      # build data.js cho dashboard
data/
  raw/<date>.json         # raw data
  daily/<date>.md         # phân tích trong ngày
  monthly/<YYYY-MM>.md    # tổng kết tháng
dashboard/
  index.html              # dashboard chính
  data.js                 # generated, không sửa tay
CLAUDE.md                 # project context cho Claude
```

## Troubleshooting

**Scrape investing.com bị block?**
- Investing.com geo-block một số quốc gia (bao gồm Việt Nam) ở tầng network. Từ IP VN sẽ bị timeout.
- Cloudflare yêu cầu cookie `cf_clearance` (chỉ cấp khi browser thật chạy JS challenge) cho POST AJAX endpoint → HTTP client thuần (curl_cffi) bị 403.
- Scraper dùng **Playwright (headless Chromium)** từ tháng 5/2026 — chạy được JS → lấy được cf_clearance → POST AJAX OK. Mỗi fetch tốn ~3-5 giây.
- Nếu fail: chỉ có FRED snapshot (31 series). Dashboard vẫn hoạt động.

**Dashboard hiện trống?**
- Chạy `python scripts/build_dashboard.py` thủ công.
- Mở DevTools console — kiểm tra `window.MACRO_DATA`.

**Không có FRED key?**
- System vẫn chạy nhưng dashboard sẽ không có chart lịch sử, chỉ có release của ngày.

## Chỉ số được theo dõi (24 series FRED)

Lạm phát: CPI, Core CPI, PCE, Core PCE, PPI
Lao động: NFP, Unemployment, Jobless Claims, AHE, JOLTS
Tăng trưởng: GDP, Retail Sales, Industrial Production, ISM Mfg, ISM Services
Niềm tin: Michigan Sentiment, Consumer Confidence
Nhà ở: Housing Starts, Existing Home Sales, Case-Shiller
Lãi suất: Fed Funds, 10Y, 2Y, 3M, 10Y-2Y spread
