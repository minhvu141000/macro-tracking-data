---
description: Thu thập, phân tích, và cập nhật dashboard cho dữ liệu vĩ mô Mỹ trong ngày
argument-hint: "[YYYY-MM-DD] (optional, mặc định hôm nay theo giờ NY)"
---

Chạy daily macro workflow. Ngày target: $ARGUMENTS (nếu rỗng thì dùng hôm nay).

Quy trình (chạy TUẦN TỰ, không parallel — mỗi bước phụ thuộc bước trước):

## Bước 1: Thu thập dữ liệu
Dùng Agent tool với `subagent_type: macro-collector` và yêu cầu thu thập cho ngày target.
Sau khi xong: xác nhận file `data/raw/<date>.json` tồn tại và hợp lệ.

## Bước 1b: Thu thập sector ETF + cross-asset + calendar
Chạy 3 script tuần tự:
```
source .venv/bin/activate && \
  python scripts/fetch_sectors.py && \
  python scripts/fetch_cross_asset.py && \
  python scripts/fetch_calendar.py
```
- `fetch_sectors.py`: 11 SPDR sectors + SPY benchmark
- `fetch_cross_asset.py`: Gold, Copper, BTC (DXY/VIX/WTI/spreads/breakeven đã trong FRED)
- `fetch_calendar.py`: earnings 55 stocks + macro release projections 21 ngày tới

Nếu Yahoo fail → cảnh báo nhưng tiếp tục flow.

## Bước 2: Phân tích
Dùng Agent tool với `subagent_type: macro-analyst`. Truyền vào prompt: "Phân tích raw data cho ngày <date>, viết báo cáo vào data/daily/<date>.md".
Đợi agent hoàn thành.

## Bước 3: Cập nhật trend signals
Trước khi gọi agent, **regenerate file tóm tắt 30 ngày** (compact ~600 tokens/report) để agent không phải đọc full 30 reports:
```
cd "/Users/tranquangminhvu/Vĩ mô Mỹ Tracking" && source .venv/bin/activate && \
  python scripts/summarize_reports.py
```
Sau đó dùng Agent tool với `subagent_type: macro-trend`. Prompt:
"Đọc **data/daily_summaries.md** trước (compact view của 30 ngày gần nhất). Sau đó nếu cần context sâu hơn cho 2-3 ngày turning point, đọc full markdown tại data/daily/<date>.md. Bổ sung phần 'Bối cảnh xu hướng' vào báo cáo data/daily/<date>.md nếu chưa đủ chi tiết. KHÔNG đọc tất cả 30 reports đầy đủ. KHÔNG tạo monthly report."

## Bước 3b: Auto-update edu theory với indicators mới
Chạy Bash để detect chỉ số mới chưa có trong edu file + auto-add stub:
```
cd "/Users/tranquangminhvu/Vĩ mô Mỹ Tracking" && source .venv/bin/activate && \
  python scripts/update_theory.py --auto-stub
```
- Script extract release names từ tất cả data/raw/*.json
- So sánh với data/macro_theory.json
- Stub mới sẽ vào category "Cần Bổ Sung (Auto-detected)" trong edu dashboard
- User có thể tự bổ sung nội dung hoặc nhờ Claude viết cho từng stub
- Nếu không có chỉ số mới → script silent skip

## Bước 4: Build dashboard
Dùng Agent tool với `subagent_type: macro-dashboard`. Prompt: "Rebuild dashboard với dữ liệu mới nhất."

## Bước 5: Mở dashboard trên trình duyệt
Chạy lệnh Bash để mở cả 2 dashboard trên Google Chrome:
```
open -a "Google Chrome" dashboard/index.html
open -a "Google Chrome" dashboard/edu.html
```
Lệnh này sẽ mở cả Dashboard Tracking và Dashboard Học Tập trên trình duyệt Google Chrome.

## Bước 5b: Auto-backup lên GitHub
Chạy lệnh Bash (gói tất cả vào 1 lệnh để skip nếu nothing to commit):
```
git add data/ dashboard/data.js && \
  git diff --cached --quiet || \
  (git -c user.email="minhvu141000@gmail.com" -c user.name="minhvu141000" \
    commit -m "Daily macro <date>" && git push origin main)
```

Nếu không có thay đổi → `git diff --cached --quiet` trả về 0 → skip commit (an toàn).
Nếu có thay đổi → commit với message `Daily macro YYYY-MM-DD` rồi push.
Nếu push fail (network, conflict) → cảnh báo user nhưng KHÔNG dừng flow (data đã saved local).

## Bước 6: Báo cáo tóm tắt
Sau khi 5 bước xong, in cho user:
- Số chỉ số US công bố hôm nay
- 1-2 câu key takeaway (đọc từ front-matter của daily report)
- Xác nhận dashboard đã mở
- Xác nhận đã push GitHub (hoặc note nếu fail)

## Lưu ý quan trọng
- Nếu BẤT KỲ bước nào thất bại → DỪNG và báo lỗi đầy đủ. KHÔNG bỏ qua bước.
- Nếu không có FRED API key → vẫn chạy được nhưng cảnh báo user rằng dashboard sẽ thiếu chart lịch sử.
- KHÔNG chạy 4 agent đồng thời. Mỗi agent phải đợi agent trước hoàn thành.
