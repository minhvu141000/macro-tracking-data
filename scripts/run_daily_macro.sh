#!/bin/bash
# Tự động chạy /daily-macro headless sau khi US đóng cửa.
# Gọi bởi launchd (com.macrotracking.daily) — Thứ 2..6, 14:00 giờ Vancouver
# (US đóng 13:00 PT → chạy sau 1h để data settle).
#
# Chỉ tích lũy + viết báo cáo; bước push GitHub đã nằm trong /daily-macro.
# Test thủ công:  bash "scripts/run_daily_macro.sh"
set -u

PROJECT="/Users/tranquangminhvu/Vĩ mô Mỹ Tracking"
LOG_DIR="$PROJECT/data/automation_logs"
LOCK="$LOG_DIR/.run.lock"
mkdir -p "$LOG_DIR"

# claude (~/.local/bin) + node/git (homebrew) + system paths cho môi trường launchd tối giản
export PATH="/Users/tranquangminhvu/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export HOME="/Users/tranquangminhvu"

TS="$(date +%Y-%m-%d_%H%M%S)"
LOG="$LOG_DIR/daily_$TS.log"

# Chống chạy chồng (nếu lần trước chưa xong). mkdir là atomic.
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "[$TS] Bỏ qua: một lần chạy khác đang diễn ra ($LOCK)" >> "$LOG"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

cd "$PROJECT" || { echo "cd fail" >> "$LOG"; exit 1; }

{
  echo "=== Daily macro auto-run $TS ($(date +%Z)) ==="
  echo "claude: $(command -v claude)  node: $(command -v node)"
  echo "--- bắt đầu /daily-macro (headless) ---"
  # -p: print mode (không tương tác); skip-permissions: unattended.
  claude -p "/daily-macro" --dangerously-skip-permissions
  echo "--- /daily-macro exit code: $? ---"
  echo "=== xong $(date +%Y-%m-%d_%H%M%S) ==="
} >> "$LOG" 2>&1

# Dọn log cũ > 30 ngày
find "$LOG_DIR" -name 'daily_*.log' -type f -mtime +30 -delete 2>/dev/null

exit 0
