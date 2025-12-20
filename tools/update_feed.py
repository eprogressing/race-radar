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
    norm_generic, # New generic normalizer
    now_iso,
    canonicalize_url,
    id_from_url,
    extract_bonus,
    map_category, # Legacy, might be deprecated but kept in normalize.py
    ensure_item_schema,
    parse_deadline,
    is_recent,
)

# calculate_quality_score is not exported from normalize anymore because rank_item handles it
# If update_feed still needs it, we can remove it or fix normalize.py
# In normalize.py we saw: ensure_item_schema calls rank_item
# So update_feed doesn't need to call calculate_quality_score directly if it uses ensure_item_schema
# Let's remove calculate_quality_score from import

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
        # Re-apply schema, classification and ranking
        # Note: we pass a copy to avoid mutating original if needed, but ensure_item_schema returns new dict
        new_it = ensure_item_schema(it)
        
        # Canonicalize URL/ID again to be safe
        su = canonicalize_url(new_it.get("sourceUrl"))
        if su:
            new_it["id"] = id_from_url(su)
            new_it["sourceUrl"] = su
            
        rebuilt.append(new_it)
    return rebuilt

# --- Fetchers ---

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

def fetch_generic_html(config):
    """
    Generic HTML fetcher for static sites (CUMCM, ChallengeCup, NSCSCC, etc.)
    """
    url = config.get("url")
    name = config.get("name")
    cat_fixed = config.get("category_fixed")
    
    try:
        r = requests.get(url, timeout=20)
        r.encoding = r.apparent_encoding # Fix encoding issues
    except Exception:
        return []
        
    soup = BeautifulSoup(r.text, "lxml")
    items = []
    
    # Simple heuristic: find list links
    # Improve selectors based on site later if needed
    candidates = []
    
    # Strategy: Find common list containers or just all 'a' tags
    # For now, just all reasonable links
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a.get("href")
        
        # Basic filter
        if len(text) < 4: continue
        if href.startswith("javascript"): continue
        
        # keyword filter for relevancy
        if not any(k in text for k in ["通知", "公告", "竞赛", "比赛", "报名", "大赛", "赛题", "结果", "名单"]):
            # For pure lists like NSCSCC, title might be "2025..."
            if not re.search(r"202\d", text):
                continue
                
        full_url = href if href.startswith("http") else requests.compat.urljoin(url, href)
        
        candidates.append({
            "title": text,
            "url": full_url,
            "category": [cat_fixed] if cat_fixed else [],
            "sourceName": name
        })
        
    # Dedup by URL
    dedup = {}
    for c in candidates:
        dedup[c["url"]] = c
        
    # Detail fetch (optional, for top N items)
    final_candidates = list(dedup.values())[:20] # Limit detail fetch
    
    for c in final_candidates:
        # Fetch detail for bonus/date
        try:
            # Skip non-html (files)
            if c["url"].endswith((".pdf", ".doc", ".docx", ".zip", ".rar")):
                items.append(norm_generic(c, name))
                continue
                
            rd = requests.get(c["url"], timeout=10)
            rd.encoding = rd.apparent_encoding
            sd = BeautifulSoup(rd.text, "lxml")
            # Extract main text
            # Try to find main content area or just body text
            content = sd.body.get_text(separator="\n", strip=True) if sd.body else ""
            c["text"] = content[:5000] # Pass text to normalizer
        except:
            pass
            
        items.append(norm_generic(c, name))
        
    return items

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
            
    # Sample up to 10 details per page roughly (pages*10)
    limit = pages * 10
    
    for full in list(detail_links)[:limit]: 
        try:
            rr = requests.get(full, timeout=20)
            ss = BeautifulSoup(rr.text, "lxml")
            
            # Title fallback
            h1 = ss.find("h1")
            title = h1.get_text(strip=True) if h1 else (ss.title.get_text(strip=True) if ss.title else "")
            
            text_all = ss.get_text(" ", strip=True)
            
            # Use generic normalizer which handles bonus/date/schema
            item_data = {
                "title": title,
                "url": full,
                "text": text_all,
                "category": [fixed_cat] if fixed_cat else []
            }
            items.append(norm_generic(item_data, "52竞赛网"))
            
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
    
    items = []
    
    # HTML parsing fallback
    links = set()
    for a in soup.find_all("a"):
        href = a.get("href") or ""
        if href.startswith("/competitions/") and len(href.split("/")) >= 3:
            links.add(href.split("?")[0])
            
    for href in list(links)[:20]:
        full = f"https://www.kaggle.com{href}"
        try:
            rr = requests.get(full, timeout=20, headers=headers)
            ss = BeautifulSoup(rr.text, "lxml")
            title = ss.title.get_text(strip=True).replace(" | Kaggle", "") if ss.title else "Kaggle Competition"
            text_all = ss.get_text(" ", strip=True)
            
            # Try to get bonus from header/metadata if possible
            # Just pass text to normalizer
            
            item_data = {
                "title": title,
                "url": full,
                "text": text_all,
                "category": ["AI数据"],
                "sourceName": "Kaggle"
            }
            items.append(norm_generic(item_data, "Kaggle"))
            
        except Exception:
            continue
    return items

def fetch_saikr(config):
    base_url = config.get("url")
    pages = config.get("pages", 1)
    fixed_cat = config.get("category_fixed")
    
    items = []
    detail_links = set()
    
    for p in range(1, pages + 1):
        u = f"{base_url}?page={p}" if "?" not in base_url else f"{base_url}&page={p}"
        try:
            r = requests.get(u, timeout=20)
            soup = BeautifulSoup(r.text, "lxml")
            for li in soup.find_all("li"):
                # Check if it's a competition list item
                a = li.find("a", href=True)
                if not a: continue
                href = a['href']
                if re.match(r"https?://www\.saikr\.com/vse/\d+", href) or href.startswith("/vse/"):
                    if href.startswith("/"):
                        full = f"https://www.saikr.com{href}"
                    else:
                        full = href
                    detail_links.add(full)
        except Exception:
            continue
            
    for full in list(detail_links):
        try:
            rr = requests.get(full, timeout=20)
            ss = BeautifulSoup(rr.text, "lxml")
            title = ss.title.get_text(strip=True).split("-")[0].strip() if ss.title else "赛氪竞赛"
            text_all = ss.get_text(" ", strip=True)
            
            item_data = {
                "title": title,
                "url": full,
                "text": text_all,
                "category": [fixed_cat] if fixed_cat else []
            }
            items.append(norm_generic(item_data, "赛氪"))
            
        except Exception:
            continue
    return items

def fetch_tianchi(config):
    # Tianchi is tricky (JS), try best effort HTML
    # Or static fallback
    return fetch_generic_html(config)

FETCHERS = {
    "codeforces": fetch_codeforces,
    "atcoder": fetch_atcoder,
    "drivendata": fetch_drivendata,
    "cumcm": fetch_generic_html,
    "challengecup": fetch_generic_html,
    "52jingsai": fetch_52jingsai,
    "kaggle": fetch_kaggle,
    "saikr": fetch_saikr,
    "generic_html": fetch_generic_html, # For simple static sites
    # Map new sources to generic fetcher for now
    "nscscc": fetch_generic_html,
    "lanqiao": fetch_generic_html,
    "tianchi": fetch_generic_html,
    "comap": fetch_generic_html,
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
            # Update fields, prefer new info if valid
            # Especially update rank info/tags
            for k in ["title", "bonusAmount", "bonusText", "deadline", "category", "tags", "qualityScore", "rankReasons", "isWhitelist", "level"]:
                if i.get(k):
                    existing[k] = i[k]
            
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
    ap.add_argument("--dry-run", action="store_true", help="Print stats and JSON without saving")
    ap.add_argument("--ci", action="store_true", help="CI mode: force save, verbose logging, strict validation")
    args = ap.parse_args()
    
    cfg = load_sources()
    feed = load_feed()
    feed["items"] = rebuild_existing(feed.get("items", []))
    all_new = []
    stats = {}
    
    print(f"Starting update... Current items: {len(feed['items'])}")
    
    for s in cfg.get("sources", []):
        if not s.get("enabled"):
            continue
        t = s.get("type")
        name = s.get("name")
        
        # Dispatcher logic: map types to functions
        fn = FETCHERS.get(t)
        # Fallback for generic sources defined in YAML
        if not fn and t in ["cumcm", "challengecup", "nscscc", "lanqiao", "tianchi", "comap"]:
             fn = fetch_generic_html
             
        if not fn:
            continue
            
        try:
            print(f"Fetching {name}...")
            res = fn(s) # pass full config dict
            fetched = len(res)
            # category filter: enforce only 4 classes
            filtered = []
            drop_reasons = {"category_mismatch": 0, "expired": 0}
            
            for it in res:
                # 1. Check expiration (soft delete from NEW fetch, not history)
                # If deadline exists and is > 30 days ago, skip
                dl = it.get("deadline")
                if dl and not is_recent(it.get("summary", ""), dl):
                     drop_reasons["expired"] += 1
                     continue
                     
                # 2. Check category
                cats = it.get("category") or []
                if any(c in ["编程","数学建模","AI数据","创新创业"] for c in cats):
                    filtered.append(it)
                else:
                    drop_reasons["category_mismatch"] += 1
                    
            kept = len(filtered)
            dropped = fetched - kept
            stats[name] = {
                "fetched": fetched, 
                "kept": kept, 
                "dropped": dropped,
                "reasons": {k:v for k,v in drop_reasons.items() if v > 0}
            }
            if dropped > 0:
                print(f"  Dropped {dropped} items from {name}. Reasons: {stats[name]['reasons']}")
                
            all_new.extend(filtered)
        except Exception as e:
            print(f"  Error fetching {name}: {e}")
            stats[name] = {"fetched": 0, "kept": 0, "dropped": 0, "error": str(e)}
            continue
            
    merged_items, added = merge_items(feed.get("items", []), all_new)
    added_count = len(added)
    
    # Sort by qualityScore desc, then deadline asc (urgent first), then createdAt desc
    # deadline sort is tricky with empty strings. 
    # Strategy: High quality first. Within same quality, close deadline first.
    def sort_key(x):
        qs = x.get("qualityScore", 0)
        dl = x.get("deadline", "")
        # Future deadline < No deadline < Past deadline?
        # Actually: Urgent deadline (close future) should boost score?
        # Score already includes deadline urgency.
        # So just sort by score.
        # Secondary: createdAt
        return (qs, x.get("createdAt", ""))
        
    merged_items.sort(key=sort_key, reverse=True)
    
    # Print summary stats
    cat_stats = {"编程":0, "数学建模":0, "AI数据":0, "创新创业":0}
    for it in merged_items:
        for c in it.get("category", []):
            if c in cat_stats: cat_stats[c] += 1
    
    # Top sources stats
    src_stats = {}
    for it in merged_items:
        src = it.get("sourceName", "unknown")
        src_stats[src] = src_stats.get(src, 0) + 1
    top_sources = sorted(src_stats.items(), key=lambda x: x[1], reverse=True)[:10]
    
    summary = {
        "total_items": len(merged_items),
        "added": added_count,
        "categories": cat_stats,
        "top_sources": dict(top_sources),
        "source_details": stats
    }
    
    print("=== Update Summary ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    
    if args.dry_run:
        print("Dry-run mode: skipping save.")
        # preview top 5
        print("Top 10 items preview:")
        for x in merged_items[:10]:
            print(f"  [{x.get('qualityScore')}] {x['title']} ({x['sourceName']}) - {x.get('bonusText')} - {x.get('rankReasons')}")
        sys.exit(0)
        
    # CI mode or normal mode: ALWAYS SAVE if we have items
    # Validation
    if len(merged_items) == 0:
        if args.ci:
            print("Error: No items found after merge. CI failed.")
            sys.exit(1)
        else:
            print("Warning: No items found.")
    
    # Update feed
    feed["items"] = merged_items
    feed["updatedAt"] = now_iso()
    
    if args.ci:
        # Strict checks for CI
        if not feed["updatedAt"]:
            print("Error: updatedAt is empty")
            sys.exit(1)
        if len(feed["items"]) < 5: # sanity check
             print("Warning: feed items very low (<5)")
             
    save_feed(feed)
    print(f"Feed saved. Total items: {len(feed['items'])}. UpdatedAt: {feed['updatedAt']}")

if __name__ == "__main__":
    main()
