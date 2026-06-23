#!/bin/bash
# Tự động chạy sau khi US đóng cửa. Gọi bởi launchd (com.macrotracking.daily) —
# Thứ 2..6, 14:00 giờ Vancouver (US đóng 13:00 PT → +1h để data settle).
#
# HYBRID:
#   • LUÔN cập nhật rotation snapshot (build_sector_rotation) — cần mỗi phiên để
#     engine luân chuyển dòng tiền đáng tin (giá sector chạy mỗi ngày).
#   • CHỈ chạy báo cáo LLM (/daily-macro đầy đủ) + mở Chrome KHI có chỉ số US công bố.
#     Ngày không có chỉ số → chỉ lưu snapshot + push, KHÔNG tốn token, KHÔNG mở Chrome.
#
# Test thủ công:  bash "scripts/run_daily_macro.sh"
set -u

PROJECT="/Users/tranquangminhvu/Vĩ mô Mỹ Tracking"
LOG_DIR="$PROJECT/data/automation_logs"
LOCK="$LOG_DIR/.run.lock"
mkdir -p "$LOG_DIR"

export PATH="/Users/tranquangminhvu/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export HOME="/Users/tranquangminhvu"

TS="$(date +%Y-%m-%d_%H%M%S)"
LOG="$LOG_DIR/daily_$TS.log"

if ! mkdir "$LOCK" 2>/dev/null; then
  echo "[$TS] Bỏ qua: một lần chạy khác đang diễn ra" >> "$LOG"; exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

cd "$PROJECT" || { echo "cd fail" >> "$LOG"; exit 1; }
GIT_ID=(-c user.email="minhvu141000@gmail.com" -c user.name="minhvu141000")

run() {  # chạy 1 lệnh, log, không dừng cả script nếu lỗi non-critical
  echo ">> $*"; "$@"; echo "   exit=$?"
}

{
  echo "=== Auto-run $TS ($(date +%Z)) ==="
  source .venv/bin/activate 2>/dev/null

  # 1) Thu thập dữ liệu hôm nay (raw + FRED + cycle_context) — cần để quyết định + làm snapshot
  run python scripts/collect.py || { echo "collect FAIL → dừng"; exit 1; }

  # 2) Đã có KẾT QUẢ THỰC (actual) cho phiên hôm nay chưa?
  #    Đếm release signal có actual != None — KHÔNG dùng signal_release_count (chỉ là
  #    lịch công bố, vẫn >0 cả khi phiên CHƯA đóng → tránh viết báo cáo rỗng lúc chạy bù
  #    ngoài giờ, vd nửa đêm trước khi US mở cửa).
  SIG="$(python - <<'PY'
import json, glob
fs = sorted(glob.glob("data/raw/[0-9]*.json"))
try:
    d = json.loads(open(fs[-1]).read())
    n = sum(1 for r in d.get("releases", [])
            if not r.get("is_noise") and (r.get("parsed") or {}).get("actual") is not None)
    print(n)
except Exception:
    print(-1)
PY
)"
  echo "Số chỉ số US ĐÃ CÓ kết quả thực (actual) hôm nay = $SIG"

  if [ "$SIG" -gt 0 ]; then
    # ----- ĐÃ CÓ kết quả thực → full /daily-macro (báo cáo LLM, dashboard, push, Chrome) -----
    echo "--- Có $SIG chỉ số đã công bố → chạy /daily-macro đầy đủ (headless) ---"
    claude -p "/daily-macro" --dangerously-skip-permissions
    echo "--- /daily-macro exit=$? ---"
  else
    # ----- Chưa có kết quả thực (phiên chưa đóng / ngày trống) → chỉ snapshot, BỎ báo cáo LLM -----
    echo "--- Chưa có actual nào (phiên chưa đóng hoặc ngày trống) → chỉ lưu rotation snapshot, BỎ báo cáo LLM & Chrome ---"
    run python scripts/fetch_sectors.py
    run python scripts/fetch_cross_asset.py
    run python scripts/build_surprise_index.py
    run python scripts/build_sector_rotation.py
    run python scripts/fetch_eia.py
    run python scripts/fetch_fed_forecasts.py
    run python scripts/build_dashboard.py
    DATE="$(basename "$(ls -t data/raw/[0-9]*.json | head -1)" .json)"
    git add data/ dashboard/data.js
    if ! git diff --cached --quiet; then
      git "${GIT_ID[@]}" commit -q -m "Auto rotation snapshot $DATE (no US releases)" && \
      git push origin main && echo "pushed snapshot $DATE"
    else
      echo "nothing to commit"
    fi
  fi
  echo "=== xong $(date +%Y-%m-%d_%H%M%S) ==="
} >> "$LOG" 2>&1

find "$LOG_DIR" -name 'daily_*.log' -type f -mtime +30 -delete 2>/dev/null
exit 0
