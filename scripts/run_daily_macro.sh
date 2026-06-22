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

  # 2) Có chỉ số US 'signal' công bố hôm nay không?
  SIG="$(python - <<'PY'
import json, glob
fs = sorted(glob.glob("data/raw/[0-9]*.json"))
try:
    d = json.loads(open(fs[-1]).read())
    print(int((d.get("release_summary") or {}).get("signal_release_count", 0)))
except Exception:
    print(-1)
PY
)"
  echo "signal_release_count hôm nay = $SIG"

  if [ "$SIG" -gt 0 ]; then
    # ----- NGÀY CÓ CÔNG BỐ → full /daily-macro (gồm báo cáo LLM, dashboard, push, Chrome) -----
    echo "--- Có $SIG chỉ số → chạy /daily-macro đầy đủ (headless) ---"
    claude -p "/daily-macro" --dangerously-skip-permissions
    echo "--- /daily-macro exit=$? ---"
  else
    # ----- NGÀY KHÔNG CÔNG BỐ → chỉ cập nhật rotation snapshot + dashboard + push -----
    echo "--- Không có chỉ số US → chỉ lưu rotation snapshot, BỎ báo cáo LLM & Chrome ---"
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
