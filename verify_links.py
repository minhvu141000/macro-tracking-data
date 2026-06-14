import json
import requests
from pathlib import Path

THEORY_FILE = Path("data/macro_theory.json")

def check_link(url):
    if not url or url == "#":
        return False
    try:
        # Use a real browser-like User-Agent to avoid being blocked by some sites
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=5, allow_redirects=True)
        # If it's a 404 or a very generic page that doesn't exist, we count as failure
        return response.status_code < 400
    except Exception:
        return False

def main():
    if not THEORY_FILE.exists():
        return
    
    with open(THEORY_FILE, "r") as f:
        data = json.load(f)
    
    broken_count = 0
    total_checked = 0
    
    for cat in data["categories"]:
        for ind in cat["indicators"]:
            # Check news_release_link
            if "news_release_link" in ind:
                total_checked += 1
                if not check_link(ind["news_release_link"]):
                    print(f"Broken news_release_link for {ind['id']}: {ind['news_release_link']}")
                    del ind["news_release_link"]
                    broken_count += 1
            
            # Check primary_link
            if "primary_link" in ind:
                total_checked += 1
                if not check_link(ind["primary_link"]):
                    print(f"Broken primary_link for {ind['id']}: {ind['primary_link']}")
                    # We might want to keep primary links if they are semi-valid, 
                    # but the user said "loại bỏ hẳn" if not correct.
                    # However, usually primary links are safer. 
                    # Let's focus on news_release_link first as it was newly added.
    
    if broken_count > 0:
        with open(THEORY_FILE, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Removed {broken_count} broken links.")
    else:
        print("No broken news_release_links found.")

if __name__ == "__main__":
    main()
