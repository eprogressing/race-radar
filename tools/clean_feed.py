import json
from pathlib import Path

FEED_PATH = Path("feed.json")

def clean():
    if not FEED_PATH.exists():
        print("feed.json not found")
        return

    with open(FEED_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    original_count = len(data["items"])
    new_items = []
    
    for item in data["items"]:
        # Filter out example items
        if "示例" in item.get("sourceName", "") or "示例" in item.get("title", ""):
            print(f"Removing example item: {item.get('title')}")
            continue
        new_items.append(item)

    data["items"] = new_items
    removed_count = original_count - len(new_items)
    
    with open(FEED_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    print(f"Cleaned feed. Removed {removed_count} items. Remaining: {len(new_items)}")

if __name__ == "__main__":
    clean()
