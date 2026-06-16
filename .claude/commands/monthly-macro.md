---
description: Tổng hợp vĩ mô Mỹ cho 1 tháng và map sang 11 GICS sectors
argument-hint: "[YYYY-MM] (optional, mặc định tháng trước)"
---

Tổng hợp tháng vĩ mô Mỹ. Tháng target: $ARGUMENTS (nếu rỗng → tháng trước, vì cuối tháng hiện tại có thể chưa đủ data).

## Bước 1: Verify dữ liệu
- Liệt kê `data/daily/<YYYY-MM>-*.md` để đảm bảo có ≥15 daily reports cho tháng đó.
- Nếu thiếu → cảnh báo user nhưng vẫn tiếp tục với data có sẵn.

## Bước 1b: Generate compact summary index
Tạo file tóm tắt cho tháng target (loại bỏ noise, giữ regime + conviction):
```
cd "/Users/tranquangminhvu/Vĩ mô Mỹ Tracking" && source .venv/bin/activate && \
  python scripts/summarize_reports.py --month <YYYY-MM> --out data/monthly_input_<YYYY-MM>.md
```
File này ~600 tokens/ngày × N ngày = ~15-20k tokens cho cả tháng, **thay vì ~110k tokens** nếu agent đọc full reports.

## Bước 1c: Chấm điểm calls tháng trước (self-correcting feedback)
Trước khi viết calls mới, chấm calls của báo cáo tháng gần nhất với realized RS:
```
cd "/Users/tranquangminhvu/Vĩ mô Mỹ Tracking" && source .venv/bin/activate && \
  python scripts/build_scorecard.py
```
Ghi/cập nhật `data/monthly/scorecard.md` (hit rate + HIT/MISS từng sector). Agent PHẢI đọc file này để rút kinh nghiệm trước khi ra calls mới. Không chặn flow nếu chưa có monthly report nào.

## Bước 2: Tổng hợp tháng
Dùng Agent tool với `subagent_type: macro-trend`. Prompt:
"Viết báo cáo tháng cho <YYYY-MM>. 

**WORKFLOW TỐI ƯU TOKEN:**
1. Đọc **data/monthly_input_<YYYY-MM>.md** trước (compact summary của all reports tháng đó với front-matter + Tóm tắt + Conviction calls)
2. Đọc latest FRED snapshot tại data/raw/<latest>.json (chỉ 1 file, ~9k tokens với derived metrics đã pre-compute)
3. Nếu cần context sâu hơn cho 3-5 ngày 'turning point' (regime shift, big surprise, conviction change), đọc full markdown của những ngày đó tại data/daily/<date>.md
4. **KHÔNG đọc đầy đủ tất cả daily reports** — sẽ tốn 100k+ tokens không cần thiết
5. Đọc **data/monthly/scorecard.md** (hit rate calls tháng trước) + **data/raw/<latest>.json** block `cycle_context` (Sahm + đường cong lợi suất). Nêu rõ trong báo cáo: tháng trước call nào SAI và điều chỉnh gì lần này; chu kỳ đang ở đâu (Sahm/curve).

Output vào data/monthly/<YYYY-MM>.md theo template trong agent definition. Đặc biệt chú ý phần 11 GICS sector stance — phải có lý do định lượng (RS, MA cross, sector reaction tới các catalyst trong tháng)."

## Bước 3: Rebuild dashboard
Dùng Agent tool với `subagent_type: macro-dashboard`. Prompt: "Rebuild dashboard để hiển thị monthly report mới."

## Bước 3b: Auto-backup lên GitHub
Chạy Bash:
```
git add data/ dashboard/data.js && \
  git diff --cached --quiet || \
  (git -c user.email="minhvu141000@gmail.com" -c user.name="minhvu141000" \
    commit -m "Monthly macro <YYYY-MM>" && git push origin main)
```

## Bước 4: Báo cáo cho user
- In key_takeaway, regime, fed_stance từ front-matter báo cáo tháng
- In top 3 conviction calls từ section "Sector winners/losers"
- Đường dẫn tới báo cáo `data/monthly/<YYYY-MM>.md`
- Xác nhận đã push GitHub
