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

## Bước 2: Generate weekly report

Dùng Agent tool với `subagent_type: macro-weekly`. Prompt:

"Tạo weekly macro report cho Chủ Nhật <date>. Working directory: /Users/tranquangminhvu/Vĩ mô Mỹ Tracking. Đọc data từ: data/daily_summaries.md, data/sectors_latest.json, data/cross_asset_latest.json, data/calendar_latest.json. Viết 2 file: data/weekly/<date>.md (archive) và data/weekly/current.md (pointer)."

Đợi agent hoàn thành. Xác nhận 2 file tồn tại.

## Bước 3: Cập nhật dashboard

Chạy:
```
source .venv/bin/activate && python scripts/build_dashboard.py
```

## Bước 4: Backup lên GitHub

```
git add data/weekly/ dashboard/data.js && \
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