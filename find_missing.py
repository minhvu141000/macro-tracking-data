import json
from datetime import date, timedelta
from pathlib import Path
import subprocess

start = date(2026, 5, 21)
end = date(2026, 6, 11)
daily_dir = Path("/Users/tranquangminhvu/Vĩ mô Mỹ Tracking/data/daily")
raw_dir = Path("/Users/tranquangminhvu/Vĩ mô Mỹ Tracking/data/raw")
scripts_dir = Path("/Users/tranquangminhvu/Vĩ mô Mỹ Tracking/scripts")

missing_with_events = []

curr = start
while curr <= end:
    curr_str = curr.isoformat()
    if not (daily_dir / f"{curr_str}.md").exists() and curr.weekday() < 5:  # Monday to Friday
        # Collect data
        subprocess.run(["/Users/tranquangminhvu/Vĩ mô Mỹ Tracking/.venv/bin/python", str(scripts_dir / "collect.py"), "--date", curr_str], check=False, capture_output=True)
        raw_file = raw_dir / f"{curr_str}.json"
        if raw_file.exists():
            with open(raw_file, "r") as f:
                data = json.load(f)
                if data.get("releases"):
                    missing_with_events.append(curr_str)
    curr += timedelta(days=1)

print("MISSING DAYS WITH MACRO EVENTS:", missing_with_events)
