Chạy weekly macro workflow. Ngày Sunday target: $ARGUMENTS (nếu rỗng thì tự tính Chủ Nhật gần nhất).

## Bước 1: Refresh data (nếu cần)

Kiểm tra freshness của sector/cross-asset data:
```
python3 -c "
import json, datetime
d = json.load(open('data/sectors_latest.json'))
fetched = d.get('fetched_at', '')[:10]
today = datetime.date.today().isoformat()
delta = (datetime.date.today() - datetime.date.fromisoformat(fetched)).days if fetched else 99
print(f'sectors age: {delta} days')
if delta > 1: print('STALE — cần refresh')
else: print('FRESH — skip')
"
```

Nếu data cũ > 1 ngày → chạy refresh:
```
source .venv/bin/activate && \
  python scripts/fetch_sectors.py && \
  python scripts/fetch_cross_asset.py && \
  python scripts/fetch_calendar.py
```

Nếu data fresh → skip.

## Bước 1b: Xác nhận rotation (persistence — TẦNG VERDICT)

Chạy engine xác nhận: đọc daily evidence (`sector_rotation_history.json`) qua ~10 phiên, lọc tín hiệu BỀN → verdict tất định cho stock-picker:
```
cd "/Users/tranquangminhvu/Vĩ mô Mỹ Tracking" && source .venv/bin/activate && \
  python scripts/build_rotation_confirm.py
```
- Ghi `data/sector_rotation_confirmed.json`: `confirmed_phase` (CONFIRMED_IN / EARLY_FORMING / FADING / AVOID / NEUTRAL) + `confidence` + `persistence` (macro_pos_days, mom_pos_days, trend) cho 11 sector.
- Nếu in ra `INSUFFICIENT_HISTORY` (chưa đủ ~4 phiên daily snapshot) → báo cho user, weekly vẫn chạy nhưng nêu rõ rotation chưa đủ lịch sử để xác nhận. Không chặn flow.

## Bước 1c: Chấm điểm engine (vòng phản hồi)

Backtest tự kiểm: forward RS sau khi engine chấm điểm → engine có thực sự bắt rotation đúng không?
```
cd "/Users/tranquangminhvu/Vĩ mô Mỹ Tracking" && source .venv/bin/activate && \
  python scripts/build_rotation_scorecard.py
```
- Ghi `data/monthly/rotation_engine_scorecard.md` + `data/rotation_engine_scorecard.json`: hit rate hướng + **edge** (top3−bottom3 forward RS) ở 5/10 phiên.
- Đọc `edge`: dương = thứ hạng engine có giá trị; âm = engine đang anti-predictive (cần thêm dữ liệu thật hoặc hiệu chỉnh). Nêu 1 dòng trong Narrative weekly. Không chặn flow.

## Bước 2: Generate weekly report

Dùng Agent tool với `subagent_type: macro-weekly`. Prompt:

"Tạo weekly macro report cho Chủ Nhật <date>. Working directory: /Users/tranquangminhvu/Vĩ mô Mỹ Tracking. NGUỒN CHÍNH cho rotation verdict: data/sector_rotation_confirmed.json (đã lọc persistence). Đọc thêm: data/daily_summaries.md, data/sectors_lite.json, data/cross_asset_lite.json, data/calendar_latest.json (dùng bản *_lite.json — đã bỏ history arrays). Neo cột Stance theo confirmed_phase; section Rotation Focus lấy từ confirmed_in/early_forming/fading. Viết 2 file: data/weekly/<date>.md (archive) và data/weekly/current.md (pointer)."

Đợi agent hoàn thành. Xác nhận 2 file tồn tại.

## Bước 3: Cập nhật dashboard

Chạy:
```
source .venv/bin/activate && python scripts/build_dashboard.py
```

## Bước 4: Backup lên GitHub

```
git add data/weekly/ data/sector_rotation_confirmed.json data/monthly/rotation_engine_scorecard.md data/rotation_engine_scorecard.json dashboard/data.js && \
  git diff --cached --quiet || \
  (git -c user.email="minhvu141000@gmail.com" -c user.name="minhvu141000" \
    commit -m "Weekly macro <date>" && git push origin main)
```

## Bước 5: Báo cáo tóm tắt

In cho user:
- Xác nhận 2 file weekly đã tạo
- 1 câu key_takeaway từ frontmatter
- Sector stances summary (top 3 OW + top 2 UW)
- Catalyst quan trọng nhất tuần tới
- Xác nhận đã push GitHub