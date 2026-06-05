---
description: Tổng hợp vĩ mô Mỹ cho 1 tháng và map sang 11 GICS sectors
argument-hint: "[YYYY-MM] (optional, mặc định tháng trước)"
---

Tổng hợp tháng vĩ mô Mỹ. Tháng target: $ARGUMENTS (nếu rỗng → tháng trước, vì cuối tháng hiện tại có thể chưa đủ data).

## Bước 1: Verify dữ liệu
- Liệt kê `data/daily/<YYYY-MM>-*.md` để đảm bảo có ≥15 daily reports cho tháng đó.
- Nếu thiếu → cảnh báo user nhưng vẫn tiếp tục với data có sẵn.

## Bước 2: Tổng hợp tháng
Dùng Agent tool với `subagent_type: macro-trend`. Prompt:
"Viết báo cáo tháng cho <YYYY-MM>. Đọc TẤT CẢ daily reports trong tháng, đọc FRED snapshot từ data/raw/. Output vào data/monthly/<YYYY-MM>.md theo template trong agent definition. Đặc biệt chú ý phần 11 GICS sector stance — phải có lý do định lượng."

## Bước 3: Rebuild dashboard
Dùng Agent tool với `subagent_type: macro-dashboard`. Prompt: "Rebuild dashboard để hiển thị monthly report mới."

## Bước 3b: Auto-backup lên GitHub
Chạy Bash:
```
cd "/Users/tranquangminhvu/Vĩ mô Mỹ Tracking" && \
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
