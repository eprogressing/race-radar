import argparse
import json
import sys
from pathlib import Path
import time
import requests
import yaml
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import re

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
from tools.normalize import (
    norm_codeforces,
    norm_atcoder,
    norm_drivendata,
    norm_cumcm,
    norm_challengecup,
    now_iso,
    canonicalize_url,
    id_from_url,
    extract_bonus,
    map_category,
    ensure_item_schema,
    parse_deadline,
    is_recent
)

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

def rebuild_existing(feed_items):
    rebuilt = []
    for it in feed_items:
        it = ensure_item_schema(it)
        su = canonicalize_url(it.get("sourceUrl"))
        if su:
            it["id"] = id_from_url(su)
            it["sourceUrl"] = su
        # normalize categories to 4 classes
        cats = map_category(it.get("title"), it.get("sourceName"), it.get("summary"))
        # retain existing category if valid, else overwrite
        valid_cats = [c for c in (it.get("category") or []) if c in ["编程","数学建模","AI数据","创新创业"]]
        if valid_cats:
            it["category"] = valid_cats
        elif cats:
            it["category"] = cats
        
        # createdAt fallback
        if not it.get("createdAt"):
            it["createdAt"] = now_iso()
        # bonus defaults
        if it.get("bonusAmount") is None:
            it["bonusAmount"] = 0
        if not it.get("bonusText"):
            it["bonusText"] = "-"
        rebuilt.append(it)
    return rebuilt

def fetch_codeforces(config):
    url = config.get("url")
    r = requests.get(url, timeout=20)
    data = r.json()
    items = []
    if data.get("status") == "OK":
        for c in data.get("result", []):
            if c.get("phase") == "BEFORE":
                items.append(norm_codeforces(c))
    return items

def fetch_atcoder(config):
    url = config.get("url")
    r = requests.get(url, timeout=20)
    data = r.json()
    now_ts = int(time.time())
    items = []
    for c in data:
        if c.get("start_epoch_second", 0) > now_ts:
            items.append(norm_atcoder(c))
    return items

def fetch_drivendata(config):
    url = config.get("url")
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

def fetch_cumcm(config):
    url = config.get("url")
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
            items.append(norm_cumcm({"slug": slug, "title": txt, "url": full, "text": txt}))
    dedup = {}
    for x in items[:20]:
        dedup[x["id"]] = x
    return list(dedup.values())

def fetch_challengecup(config):
    url = config.get("url")
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
            items.append(norm_challengecup({"slug": slug, "title": txt, "url": full, "text": txt}))
    dedup = {}
    for x in items[:30]:
        dedup[x["id"]] = x
    return list(dedup.values())

def fetch_52jingsai(config):
    base_url = config.get("url")
    pages = config.get("pages", 1)
    fixed_cat = config.get("category_fixed")
    
    items = []
    detail_links = set()
    
    # Page iteration
    for p in range(1, pages + 1):
        if p == 1:
            u = base_url
        else:
            # Handle list-17-10.html -> list-17-10-2.html
            if re.search(r"-\d+\.html$", base_url):
                u = re.sub(r"(\.html)$", f"-{p}\\1", base_url)
            else:
                continue
        try:
            r = requests.get(u, timeout=20)
            soup = BeautifulSoup(r.text, "lxml")
            # Robust selector: find all links matching article pattern
            for a in soup.find_all("a"):
                href = a.get("href") or ""
                if re.match(r"/?article-\d+(-\d+)?\.html$", href):
                    full = f"https://www.52jingsai.com/{href.lstrip('/')}" if not href.startswith("http") else href
                    detail_links.add(full)
        except Exception:
            continue
            
    for full in list(detail_links)[:30]: # Limit per source config
        try:
            rr = requests.get(full, timeout=20)
            ss = BeautifulSoup(rr.text, "lxml")
            
            # Title fallback
            h1 = ss.find("h1")
            title = h1.get_text(strip=True) if h1 else (ss.title.get_text(strip=True) if ss.title else "")
            
            text_all = ss.get_text(" ", strip=True)
            
            # Bonus
            bonus_amt, bonus_txt = extract_bonus(text_all)
            
            # Deadline
            deadline = parse_deadline(text_all)
            
            # Category
            cat = []
            if fixed_cat:
                cat = [fixed_cat]
            else:
                cat = map_category(title, "52竞赛网", text_all[:500])
                
            if not cat:
                continue
                
            # Quality filter
            if not is_recent(text_all, deadline):
                continue
                
            item = ensure_item_schema({
                "id": id_from_url(full),
                "title": title,
                "bonusAmount": bonus_amt,
                "bonusText": bonus_txt or "-",
                "deadline": deadline,
                "category": cat,
                "tags": [],
                "cover": "",
                "sourceName": "52竞赛网",
                "sourceUrl": canonicalize_url(full),
                "summary": "",
                "createdAt": now_iso()
            })
            items.append(item)
        except Exception:
            continue
    return items

def fetch_kaggle(config):
    url = config.get("url")
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9"
    }
    try:
        r = requests.get(url, timeout=20, headers=headers)
    except Exception:
        return []
    soup = BeautifulSoup(r.text, "lxml")
    links = set()
    for a in soup.find_all("a"):
        href = a.get("href") or ""
        if href.startswith("/competitions/") and len(href.split("/")) >= 3:
            links.add(href.split("?")[0])
    items = []
    for href in list(links)[:30]:
        full = f"https://www.kaggle.com{href}"
        try:
            rr = requests.get(full, timeout=20, headers=headers)
            ss = BeautifulSoup(rr.text, "lxml")
            title = ss.title.get_text(strip=True) if ss.title else "Kaggle Competition"
            text_all = ss.get_text(" ", strip=True)
            bonus_amt, bonus_txt = extract_bonus(text_all)
            # try next_data
            next_data = ss.find("script", id="__NEXT_DATA__")
            deadline = ""
            if next_data and next_data.string:
                try:
                    jd = json.loads(next_data.string)
                    # heuristic
                    comp = jd.get("props", {}).get("pageProps", {}).get("competition", {})
                    dl = comp.get("deadline") or comp.get("deadlineDate")
                    if isinstance(dl, str):
                        deadline = dl[:10]
                except Exception:
                    pass
            cat = ["AI数据"]
            item = ensure_item_schema({
                "id": id_from_url(full),
                "title": title,
                "bonusAmount": bonus_amt,
                "bonusText": bonus_txt or "-",
                "deadline": deadline,
                "category": cat,
                "tags": ["Kaggle"],
                "cover": "",
                "sourceName": "Kaggle",
                "sourceUrl": canonicalize_url(full),
                "summary": "",
                "createdAt": now_iso()
            })
            items.append(item)
        except Exception:
            continue
    return items

def fetch_saikr(config):
    base_url = config.get("url")
    pages = config.get("pages", 1)
    
    items = []
    detail_links = set()
    
    for p in range(1, pages + 1):
        u = f"{base_url}&page={p}"
        try:
            r = requests.get(u, timeout=20)
            soup = BeautifulSoup(r.text, "lxml")
            for a in soup.find_all("a"):
                href = a.get("href") or ""
                if re.match(r"https?://www\.saikr\.com/vse/\d+", href) or href.startswith("/vse/"):
                    if href.startswith("/"):
                        full = f"https://www.saikr.com{href}"
                    else:
                        full = href
                    detail_links.add(full)
        except Exception:
            continue
            
    for full in list(detail_links)[:40]:
        try:
            rr = requests.get(full, timeout=20)
            ss = BeautifulSoup(rr.text, "lxml")
            title = ss.title.get_text(strip=True) if ss.title else "赛氪竞赛"
            text_all = ss.get_text(" ", strip=True)
            
            # Deadline
            deadline = parse_deadline(text_all)
            
            # Bonus
            bonus_amt, bonus_txt = extract_bonus(text_all)
            
            # Category
            cat = map_category(title, "赛氪", text_all[:500])
            if not cat:
                continue
                
            # Quality filter
            if not is_recent(text_all, deadline):
                continue
                
            item = ensure_item_schema({
                "id": id_from_url(full),
                "title": title,
                "bonusAmount": bonus_amt,
                "bonusText": bonus_txt or "-",
                "deadline": deadline,
                "category": cat,
                "tags": ["赛氪"],
                "cover": "",
                "sourceName": "赛氪",
                "sourceUrl": canonicalize_url(full),
                "summary": "",
                "createdAt": now_iso()
            })
            items.append(item)
        except Exception:
            continue
    return items

FETCHERS = {
    "codeforces": fetch_codeforces,
    "atcoder": fetch_atcoder,
    "drivendata": fetch_drivendata,
    "cumcm": fetch_cumcm,
    "challengecup": fetch_challengecup,
    "52jingsai": fetch_52jingsai,
    "kaggle": fetch_kaggle,
    "saikr": fetch_saikr,
}

def merge_items(old_items, new_items):
    # index by canonical_url
    by_url = {}
    for it in old_items:
        cu = canonicalize_url(it.get("sourceUrl"))
        by_url[cu] = it
    merged = list(old_items)
    added = []
    for i in new_items:
        cu = canonicalize_url(i.get("sourceUrl"))
        if cu in by_url:
            existing = by_url[cu]
            # fill missing fields only
            for k in ["title","bonusAmount","bonusText","deadline","category","tags","cover","sourceName","summary"]:
                if not existing.get(k) and i.get(k):
                    existing[k] = i[k]
            # update id to canonical
            existing["id"] = id_from_url(cu)
            # preserve earliest createdAt
            if not existing.get("createdAt"):
                existing["createdAt"] = i.get("createdAt") or now_iso()
        else:
            added.append(i)
            merged.append(i)
            by_url[cu] = i
    return merged, added

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = load_sources()
    feed = load_feed()
    feed["items"] = rebuild_existing(feed.get("items", []))
    all_new = []
    stats = {}
    
    for s in cfg.get("sources", []):
        if not s.get("enabled"):
            continue
        t = s.get("type")
        name = s.get("name")
        fn = FETCHERS.get(t)
        if not fn:
            continue
        try:
            res = fn(s) # pass full config dict
            fetched = len(res)
            # category filter: enforce only 4 classes
            filtered = []
            for it in res:
                cats = it.get("category") or []
                if any(c in ["编程","数学建模","AI数据","创新创业"] for c in cats):
                    filtered.append(it)
            kept = len(filtered)
            dropped = fetched - kept
            stats[name] = {"fetched": fetched, "kept": kept, "dropped": dropped}
            all_new.extend(filtered)
        except Exception as e:
            stats[name] = {"fetched": 0, "kept": 0, "dropped": 0, "error": str(e)}
            continue
            
    merged_items, added = merge_items(feed.get("items", []), all_new)
    added_count = len(added)
    
    if args.dry_run:
        preview = {
            "version": feed.get("version", 1),
            "updatedAt": now_iso(),
            "items": merged_items
        }
        print(json.dumps({"stats": stats, "added": added_count}, ensure_ascii=False, indent=2))
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        sys.exit(0)
        
    if added_count == 0:
        sys.exit(0)
        
    feed["items"] = merged_items
    feed["updatedAt"] = now_iso()
    save_feed(feed)

if __name__ == "__main__":
    main()
