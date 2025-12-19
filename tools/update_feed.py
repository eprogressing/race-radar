import argparse
import json
import sys
from pathlib import Path
import time
import requests
import yaml
from bs4 import BeautifulSoup
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
from tools.normalize import norm_codeforces, norm_atcoder, norm_drivendata, norm_cumcm, norm_challengecup, now_iso
FEED_PATH = ROOT / "feed.json"
SOURCES_PATH = ROOT / "tools" / "sources.yaml"

def load_sources():
    with open(SOURCES_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_feed():
    if FEED_PATH.exists():
        with open(FEED_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"version": 1, "updatedAt": None, "items": []}

def save_feed(feed):
    with open(FEED_PATH, "w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False, indent=2)

def fetch_codeforces(url):
    r = requests.get(url, timeout=20)
    data = r.json()
    items = []
    if data.get("status") == "OK":
        for c in data.get("result", []):
            if c.get("phase") == "BEFORE":
                items.append(norm_codeforces(c))
    return items

def fetch_atcoder(url):
    r = requests.get(url, timeout=20)
    data = r.json()
    now_ts = int(time.time())
    items = []
    for c in data:
        if c.get("start_epoch_second", 0) > now_ts:
            items.append(norm_atcoder(c))
    return items

def fetch_drivendata(url):
    r = requests.get(url, timeout=20)
    soup = BeautifulSoup(r.text, "lxml")
    items = []
    for a in soup.select('a[href^="/competitions/"]'):
        href = a.get("href")
        text = a.get_text(strip=True)
        if not text:
            continue
        slug = href.strip("/").split("/")[1] if "/" in href.strip("/") else href.strip("/")
        items.append(norm_drivendata({"slug": slug, "title": text, "url": f"https://www.drivendata.org{href}"}))
    dedup = {}
    for x in items:
        dedup[x["id"]] = x
    return list(dedup.values())

def fetch_cumcm(url):
    r = requests.get(url, timeout=20)
    soup = BeautifulSoup(r.text, "lxml")
    items = []
    for a in soup.find_all("a"):
        txt = a.get_text(strip=True)
        href = a.get("href")
        if not href or not txt:
            continue
        if ("通知" in txt) or ("公告" in txt):
            full = href if href.startswith("http") else f"https://www.mcm.edu.cn/{href.lstrip('/')}"
            slug = Path(full).stem
            items.append(norm_cumcm({"slug": slug, "title": txt, "url": full}))
    dedup = {}
    for x in items[:20]:
        dedup[x["id"]] = x
    return list(dedup.values())

def fetch_challengecup(url):
    r = requests.get(url, timeout=20)
    soup = BeautifulSoup(r.text, "lxml")
    items = []
    for a in soup.find_all("a"):
        txt = a.get_text(strip=True)
        href = a.get("href")
        if not href or not txt:
            continue
        if ("通知" in txt) or ("公告" in txt):
            if href.startswith("http"):
                full = href
            else:
                full = f"https://2025.tiaozhanbei.net/{href.lstrip('/')}"
            slug = Path(full).stem
            items.append(norm_challengecup({"slug": slug, "title": txt, "url": full}))
    dedup = {}
    for x in items[:30]:
        dedup[x["id"]] = x
    return list(dedup.values())

FETCHERS = {
    "codeforces": fetch_codeforces,
    "atcoder": fetch_atcoder,
    "drivendata": fetch_drivendata,
    "cumcm": fetch_cumcm,
    "challengecup": fetch_challengecup,
}

def merge_items(old_items, new_items):
    old_ids = {i.get("id") for i in old_items}
    merged = list(old_items)
    added = []
    for i in new_items:
        if i.get("id") not in old_ids:
            merged.append(i)
            added.append(i)
            old_ids.add(i.get("id"))
    return merged, added

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = load_sources()
    feed = load_feed()
    all_new = []
    for s in cfg.get("sources", []):
        if not s.get("enabled"):
            continue
        t = s.get("type")
        url = s.get("url")
        fn = FETCHERS.get(t)
        if not fn:
            continue
        try:
            res = fn(url)
            all_new.extend(res)
        except Exception:
            continue
    merged_items, added = merge_items(feed.get("items", []), all_new)
    if args.dry_run:
        preview = {
            "version": feed.get("version", 1),
            "updatedAt": now_iso(),
            "items": merged_items
        }
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        sys.exit(0)
    if len(added) == 0:
        sys.exit(0)
    feed["items"] = merged_items
    feed["updatedAt"] = now_iso()
    save_feed(feed)

if __name__ == "__main__":
    main()
