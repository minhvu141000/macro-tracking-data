# US Macro Tracking — Project Guide

Hệ thống agent theo dõi và tổng hợp chỉ số vĩ mô Mỹ hàng ngày.

## Mục tiêu
- Mỗi ngày (sau khi US market đóng): thu thập các chỉ số vĩ mô Mỹ được công bố, phân tích từng chỉ số (actual vs forecast/previous, ý nghĩa, ảnh hưởng).
- Cập nhật dashboard HTML local thể hiện xu hướng các chỉ số.
- Cuối tháng: tổng hợp ra nhận định vĩ mô + map sang 11 GICS sectors.

## Nguồn dữ liệu
- **investing.com economic calendar** (scrape) — lịch công bố + actual/forecast/previous trong ngày.
- **FRED API** (St. Louis Fed) — lịch sử dài hạn của các series cốt lõi. Cần `FRED_API_KEY` trong `.env`.

## Cấu trúc thư mục
```
data/raw/YYYY-MM-DD.json        # raw scrape + FRED
data/daily/YYYY-MM-DD.md        # phân tích trong ngày
data/monthly/YYYY-MM.md         # tổng kết tháng
dashboard/index.html            # dashboard
dashboard/data.js               # dữ liệu cho Chart.js
scripts/collect.py              # scraper + FRED client
scripts/analyze.py              # tiện ích cho analyst
scripts/build_dashboard.py      # build data.js
.claude/agents/                 # 4 sub-agents
.claude/commands/               # slash commands
```

## Workflow

### Hàng ngày: `/daily-macro`
1. `macro-collector` chạy `scripts/collect.py` → lưu `data/raw/<date>.json`.
2. `macro-analyst` đọc raw → viết `data/daily/<date>.md` (phân tích từng chỉ số).
3. `macro-trend` đọc 30 ngày gần nhất → cập nhật trend signals.
4. `macro-dashboard` chạy `scripts/build_dashboard.py` → cập nhật `dashboard/data.js`.

### Cuối tháng: `/monthly-macro`
- Đọc 30 daily reports → viết `data/monthly/<YYYY-MM>.md` với:
  - Tổng quan vĩ mô (lạm phát, lao động, tăng trưởng, Fed stance)
  - Sector winners/losers theo 11 GICS
  - Risks & catalysts cho tháng tới

## Chỉ số theo dõi (US macro core)

| Nhóm | Chỉ số (FRED series ID) |
|---|---|
| Lạm phát | CPI (CPIAUCSL), Core CPI (CPILFESL), PCE (PCEPI), Core PCE (PCEPILFE), PPI Final Demand (PPIFID), Core PPI (PPIFES) |
| Lao động | NFP (PAYEMS, đọc Δ MoM), Unemp (UNRATE), Jobless Claims (ICSA), AHE (CES0500000003), JOLTS (JTSJOL) |
| Tăng trưởng | GDP Growth QoQ-ann. (A191RL1Q225SBEA), Retail Sales (RSAFS), Industrial Prod (INDPRO), ISM Mfg (NAPM), ISM Svc (NAPMNMI) |

> **Chuẩn hoá theo investing.com:** dùng đúng series thị trường quote — PPI = Final Demand (PPIFID, YoY ~6.5%) **không** phải All Commodities (PPIACO, YoY ~13%); GDP = tốc độ tăng trưởng QoQ annualized **không** phải mức $B; NFP đọc theo thay đổi MoM (Δ nghìn người) không phải mức tuyệt đối. Mỗi series có `DEFAULT_VIEW` trong dashboard để mở đúng metric headline.
| Niềm tin | Consumer Conf (CSCICP03USM665S), Michigan (UMCSENT) |
| Nhà ở | Housing Starts (HOUST), Existing Home Sales (EXHOSLUSM495S), Case-Shiller (CSUSHPINSA) |
| Fed | Fed Funds Rate (DFF), 10Y Yield (DGS10), 2Y Yield (DGS2) |

## Viết daily report bằng BẤT KỲ agent nào (kể cả agent ngoài)

Hệ thống có guardrail tất định để báo cáo đạt chất lượng dù do agent nào tạo:
1. **Đọc spec:** `.claude/agents/macro-analyst.md` — template đầy đủ + format breakdown cho từng nhóm chỉ số.
2. **Dữ liệu đã enrich sẵn:** `data/raw/<date>.json` có sẵn cho mỗi release: `parsed`, `surprise` (z_score + label), `vs_previous`, `group`, `is_noise`; block `release_summary` (`surprise_count` chuẩn + `groups_present`); và block `inflation_context` (CPI/PCE hard-data + cờ `hard_data_hot`). **Copy `surprise_count` từ đây, gộp release cùng `group` vào 1 section. Khi `hard_data_hot=true` và ngày chỉ có soft-data → PHẢI đối chiếu, không tuyên bố disinflation/dovish một chiều.**
3. **Validate bắt buộc:** sau khi viết, chạy `python scripts/validate_report.py <date>` — sửa đến khi PASS (0 ERROR). Validator bắt: surprise_count sai, thiếu nhóm chỉ số, regime_signal sai enum, thiếu frontmatter.

> Logic khó (chấm surprise, gộp nhóm) nằm trong code (`scripts/enrich_releases.py`), KHÔNG để LLM tự tính → kết quả nhất quán giữa các agent.

## Quy ước
- Mọi script Python chạy từ project root: `python scripts/<name>.py`.
- Date format mọi nơi: `YYYY-MM-DD` (ISO).
- Daily report `.md` luôn có front-matter YAML với `date`, `surprise_count`, `regime_signal`.
- Dashboard mở bằng cách double-click `dashboard/index.html`.
- **Hệ thống Deep Links:** Các chỉ số vĩ mô trong file lý thuyết (`data/macro_theory.json`) được cấu hình để dẫn trực tiếp tới trang gốc của cơ quan ban hành (`primary_link`) và biểu đồ tương tác/bản báo cáo chi tiết (`news_release_link`) như BLS, BEA, Census, Fed. Hệ thống có cơ chế tự động kiểm tra và loại bỏ các link hỏng (broken links) để đảm bảo trải nghiệm học tập trên dashboard (`dashboard/edu.html`).

## Setup
Xem `README.md` cho hướng dẫn lấy FRED API key và cài Python deps.
