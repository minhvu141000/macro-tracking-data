---
description: Tổng hợp vĩ mô Mỹ cho 1 tháng và map sang 11 GICS sectors
argument-hint: "[YYYY-MM] (optional, mặc định tháng trước)"
---

Tổng hợp tháng vĩ mô Mỹ. Tháng target: $ARGUMENTS (nếu rỗng → tháng trước, vì cuối tháng hiện tại có thể chưa đủ data).

## Bước 1: Verify dữ liệu
- Liệt kê `data/daily/<YYYY-MM>-*.md` để đảm bảo có ≥15 daily reports cho tháng đó.
- Nếu thiếu → cảnh báo user nhưng vẫn tiếp tục với data có sẵn.

## Bước 1b: Generate compact inputs cho agent
Chạy 2 script song song:
```
cd "/Users/tranquangminhvu/Vĩ mô Mỹ Tracking" && source .venv/bin/activate && \
  python scripts/summarize_reports.py --month <YYYY-MM> --out data/monthly_input_<YYYY-MM>.md && \
  python scripts/build_monthly_releases.py <YYYY-MM>
```
- `monthly_input_<YYYY-MM>.md`: front-matter + tóm tắt + conviction mỗi ngày (~15-20k tokens)
- `monthly_releases_<YYYY-MM>.md`: **bảng dữ liệu đã điền sẵn** — actual/forecast/surprise cho TẤT CẢ releases trong tháng, nhóm theo 6 category. Agent chỉ cần thêm verdict + kết luận 2 câu.

Verify: cả 2 file tồn tại và không rỗng.

## Bước 1c: Chấm điểm calls tháng trước (self-correcting feedback)
Trước khi viết calls mới, chấm calls của báo cáo tháng gần nhất với realized RS:
```
cd "/Users/tranquangminhvu/Vĩ mô Mỹ Tracking" && source .venv/bin/activate && \
  python scripts/build_scorecard.py
```
Ghi/cập nhật `data/monthly/scorecard.md` (hit rate + HIT/MISS từng sector). Agent PHẢI đọc file này để rút kinh nghiệm trước khi ra calls mới. Không chặn flow nếu chưa có monthly report nào.

## Bước 1d: Dự báo luân chuyển dòng tiền THÁNG TỚI (engine tất định)
```
cd "/Users/tranquangminhvu/Vĩ mô Mỹ Tracking" && source .venv/bin/activate && \
  python scripts/build_monthly_rotation.py
```
Engine horizon ~21 phiên (đọc `sector_rotation_history.json` + `sector_rotation_confirmed.json` + `sector_holdings_latest.json`). Ghi **2 nhóm đầu ra TÁCH BIỆT**:
- **DASHBOARD (chỉ biểu đồ):** `data/monthly_rotation_forecast_latest.json` → `build_dashboard.py` render bar chart "Dự báo luân chuyển dòng tiền" trong tab Tháng. KHÔNG prose.
- **AGENT (phân tích sâu, KHÔNG lên dashboard):** `data/monthly/rotation_forecast_<tháng tới>.json` + `.md` — đầu vào cho `fundamental-stock-picker` (forecast_phase INFLOW_LIKELY/FORMING + `stock_universe` mỗi sector). File `.md` này KHÔNG bị dashboard nhặt (chỉ `YYYY-MM.md` mới là monthly report).

Không chặn flow nếu rotation_history chưa đủ phiên (engine vẫn chạy, conviction bị cap + ghi data_quality).

> **Handoff:** sau monthly, gọi agent `fundamental-stock-picker` (xem `.claude/agents/fundamental-stock-picker.md`) với input chính là `data/monthly/rotation_forecast_<tháng>.json`.

## Bước 2: Tổng hợp tháng
Dùng Agent tool với `subagent_type: macro-trend`. Prompt:
"Viết báo cáo tháng cho <YYYY-MM>.

**FORMAT MỚI — DATA TABLE FIRST, TEXT MINIMAL:**
Báo cáo tháng dùng format bảng dữ liệu (xem template trong agent definition). KHÔNG viết prose narrative dài. Mỗi nhóm = 1 bảng liệt kê TẤT CẢ releases + 2 câu kết luận. Tối đa bảng, tối thiểu chữ.

**WORKFLOW TỐI ƯU TOKEN:**
1. Đọc **data/monthly_input_<YYYY-MM>.md** trước (compact summary — có actual/forecast/surprise cho mỗi release)
2. Đọc latest FRED snapshot tại data/raw/<latest>.json cho derived metrics (yoy, mom, mo3) + block `cycle_context`
3. Đọc **data/sectors_lite.json** (RS 1M, RS 3M, above_ma50 cho bảng sector) + **data/cross_asset_lite.json**
4. Đọc **data/monthly/scorecard.md** (hit rate calls tháng trước) — ghi vào dòng 'Scorecard' trong Cycle context của bảng sector
5. Nếu cần context turning point, đọc full markdown 2-3 ngày key tại data/daily/<date>.md
6. **KHÔNG đọc đầy đủ tất cả daily reports** — sẽ tốn 100k+ tokens

**ĐIỀN BẢNG:**
- Nhóm 1-5: **COPY nguyên bảng từ `data/monthly_releases_<YYYY-MM>.md`** (đã điền sẵn actual/forecast/surprise). Chỉ thêm [VERDICT] vào header và viết kết luận 2 câu.
- Nhóm 6 (Fed): bảng releases đã có trong monthly_releases, thêm bảng rates đầu/cuối tháng từ FRED snapshot (DFF, DGS10, DGS2, T10Y2Y, VIXCLS, BAMLH0A0HYM2, T10YIE).
- Sector table: RS 1M/3M từ sectors_lite.json (field `rs_1m`, `rs_slope`), above_ma50 field cho vs MA50 column.
- Cross-asset: từ cross_asset_lite.json (price, ret_1m fields).
- Scorecard row trong Cycle context: đọc từ data/monthly/scorecard.md.

Output vào data/monthly/<YYYY-MM>.md theo template trong agent definition."

## Bước 3: Rebuild dashboard
Dùng Agent tool với `subagent_type: macro-dashboard`. Prompt: "Rebuild dashboard để hiển thị monthly report mới."

## Bước 3b: Auto-backup lên GitHub
Chạy Bash:
```
git add data/ dashboard/data.js && \
  git diff --cached --quiet || \
  (git -c user.email="minhvu141000@gmail.com" -c user.name="minhvu141000" \
    commit -m "Monthly macro <YYYY-MM> + rotation forecast" && git push origin main)
```

## Bước 4: Báo cáo cho user
- In key_takeaway, regime, fed_stance từ front-matter báo cáo tháng
- In top 3 conviction calls từ section "Sector winners/losers"
- Đường dẫn tới báo cáo `data/monthly/<YYYY-MM>.md`
- Xác nhận đã push GitHub
