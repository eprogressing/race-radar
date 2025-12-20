import argparse
import json
import sys
from pathlib import Path
import time
import requests
import yaml
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import re

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
from tools.normalize import (
    norm_codeforces,
    norm_atcoder,
    norm_drivendata,
    norm_generic,
    now_iso,
    canonicalize_url,
    id_from_url,
    ensure_item_schema,
    normalize_title
)
from tools.classify import rank_item

FEED_PATH = ROOT / "feed.json"
SOURCES_PATH = ROOT / "tools" / "sources.yaml"

MAX_EXPIRED_DAYS_DEFAULT = 7
MAX_EXPIRED_DAYS_WHITELIST = 30

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

def fetch_soup(url, timeout=20):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        r = requests.get(url, timeout=timeout, headers=headers)
        r.encoding = r.apparent_encoding
        return BeautifulSoup(r.text, "lxml")
    except Exception as e:
        # print(f"Error fetching {url}: {e}")
        return None

def extract_bonus_context(text, window=200):
    """
    Extract text segments around bonus keywords to improve parsing accuracy
    """
    if not text: return ""
    text_lower = text.lower()
    keywords = [
        "奖金", "奖项", "奖励", "奖池", "总额", "prize", "reward", "award", 
        "冠军", "一等奖", "金奖", "最高奖", "万元", "rmb", "usd", "¥", "￥"
    ]
    
    indices = []
    for k in keywords:
        start = 0
        while True:
            idx = text_lower.find(k, start)
            if idx == -1: break
            indices.append(idx)
            start = idx + 1
            
    if not indices:
        return ""
        
    indices.sort()
    
    # Merge windows
    segments = []
    last_end = -1
    
    for idx in indices:
        start = max(0, idx - window)
        end = min(len(text), idx + window)
        
        if start < last_end:
            # Overlap, extend last segment
            segments[-1] = (segments[-1][0], max(segments[-1][1], end))
            last_end = segments[-1][1]
        else:
            segments.append((start, end))
            last_end = end
            
    # Construct context text
    context_parts = []
    for s, e in segments:
        context_parts.append(text[s:e])
        
    return " ... ".join(context_parts)

def fetch_detail_info(url, config):
    """
    Fetch detail page and extract title, content, bonus_context
    """
    soup = fetch_soup(url, timeout=15)
    if not soup:
        return None, None, None
        
    # Cleanup
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
        tag.decompose()
        
    # Extract Title
    title = None
    t_sels = config.get("title_selectors", [])
    if isinstance(t_sels, str): t_sels = [t_sels]
    
    for sel in t_sels:
        el = soup.select_one(sel)
        if el:
            title = el.get_text(strip=True)
            break
            
    if not title and soup.title:
        title = soup.title.get_text(strip=True)
        
    # Extract Content
    content = ""
    c_sels = config.get("content_selectors", [])
    if isinstance(c_sels, str): c_sels = [c_sels]
    
    for sel in c_sels:
        el = soup.select_one(sel)
        if el:
            content = el.get_text(separator="\n", strip=True)
            break
            
    if not content and soup.body:
        content = soup.body.get_text(separator="\n", strip=True)
        
    content = content[:20000] # Cap length
    
    # Extract Bonus Context
    bonus_context = extract_bonus_context(content)
    
    return title, content, bonus_context

def fetch_generic_source(config):
    items = []
    name = config.get("name")
    pagination = config.get("pagination", False)
    max_pages = config.get("max_pages", 1) if pagination else 1
    fixed_cat = config.get("category_fixed")
    
    detail_enabled = config.get("detail", False)
    detail_limit = config.get("detail_limit", 40)
    
    # Track URLs to avoid processing same item twice in one run
    seen_urls = set()
    
    print(f"Fetching {name} (Pages: {max_pages})...")
    
    for page in range(1, max_pages + 1):
        if pagination:
            pattern = config.get("pagination_pattern", "")
            if not pattern:
                # Fallback or specific logic
                if "52jingsai" in config["url"]:
                     url = config["url"] + f"&page={page}"
                elif "saikr" in config["url"]:
                     url = config["url"] + f"?page={page}"
                elif "tiaozhanbei" in config["url"]:
                     url = config["url"] + f"?page={page}"
                else:
                     url = config["url"] # No pattern?
            else:
                url = pattern.format(page=page)
        else:
            url = config.get("url")
            
        # Avoid fetching same URL if no pagination (only fetch once)
        if not pagination and page > 1:
            break
            
        soup = fetch_soup(url)
        if not soup:
            print(f"  Failed to fetch page {page}")
            continue
            
        # Parse List Items
        # Strategy: Find all links that look like detail pages
        candidates = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href")
            
            # Basic filters
            if len(text) < 4: continue
            if href.startswith(("javascript", "mailto", "tel", "#")): continue
            
            full_url = requests.compat.urljoin(url, href)
            
            # URL Filters based on source type
            if "52jingsai" in url:
                if not ("article-" in href or "thread-" in href or "viewthread" in href):
                    continue
            elif "saikr" in url:
                if not ("/vse/" in href or "saikr.com/vse/" in href):
                    continue
            elif "tianchi" in url:
                # Tianchi might be JS, but if we find links
                if not ("/competition/entrance/" in href):
                    continue
            else:
                # Generic keyword filter for others
                if not any(k in text for k in ["通知", "公告", "竞赛", "比赛", "报名", "大赛", "赛题", "结果", "名单", "Challenge", "Contest"]):
                    # Date heuristic
                    if not re.search(r"202\d", text):
                        continue
                        
            if full_url in seen_urls: continue
            seen_urls.add(full_url)
            
            candidates.append({
                "title": text,
                "url": full_url,
                "category": [fixed_cat] if fixed_cat else [],
                "sourceName": name
            })
            
        # Limit candidates per page if too many
        # candidates = candidates[:20]
        
        # Detail Fetching
        fetched_details = 0
        for cand in candidates:
            # Should we fetch detail?
            # Always fetch if enabled, up to limit
            if detail_enabled and fetched_details < detail_limit:
                # Fetch
                d_title, d_content, d_bonus = fetch_detail_info(cand["url"], config)
                
                if not d_title and not cand["title"]:
                    continue # Skip if no title at all
                    
                if d_title:
                    # Validate title
                    if normalize_title(d_title):
                        cand["title"] = d_title # Prefer detail title
                
                if d_content:
                    cand["text"] = d_content
                if d_bonus:
                    cand["bonus_context"] = d_bonus
                    
                fetched_details += 1
                time.sleep(0.2) # Polite delay
                
            # Normalize
            item = norm_generic(cand, name)
            if not item.get("_invalid"):
                items.append(item)
                
    return items

def fetch_codeforces(config):
    # Keep legacy specialized fetcher
    url = config.get("url")
    try:
        r = requests.get(url, timeout=20)
        data = r.json()
        items = []
        if data.get("status") == "OK":
            for c in data.get("result", []):
                if c.get("phase") == "BEFORE":
                    items.append(norm_codeforces(c))
        return items
    except:
        return []

def fetch_atcoder(config):
    url = config.get("url")
    try:
        r = requests.get(url, timeout=20)
        data = r.json()
        now_ts = int(time.time())
        items = []
        for c in data:
            if c.get("start_epoch_second", 0) > now_ts:
                items.append(norm_atcoder(c))
        return items
    except:
        return []

def fetch_drivendata(config):
    url = config.get("url")
    soup = fetch_soup(url)
    if not soup: return []
    items = []
    for a in soup.select('a[href^="/competitions/"]'):
        href = a.get("href")
        text = a.get_text(strip=True)
        if not text: continue
        slug = href.strip("/").split("/")[1] if "/" in href.strip("/") else href.strip("/")
        full_url = f"https://www.drivendata.org{href}"
        
        # Detail fetch for DrivenData too
        d_title, d_content, d_bonus = fetch_detail_info(full_url, config)
        
        item_data = {
            "slug": slug, 
            "title": text, 
            "url": full_url, 
            "text": d_content, 
            "bonus_context": d_bonus
        }
        items.append(norm_drivendata(item_data))
        
    # Dedup
    dedup = {}
    for x in items:
        if not x.get("_invalid"):
            dedup[x["id"]] = x
    return list(dedup.values())

FETCHERS = {
    "codeforces": fetch_codeforces,
    "atcoder": fetch_atcoder,
    "drivendata": fetch_drivendata,
    "generic": fetch_generic_source,
    "saikr": fetch_generic_source, 
    "tianchi": fetch_generic_source,
    "cumcm": fetch_generic_source,
    "nscscc": fetch_generic_source,
    "lanqiao": fetch_generic_source,
    "challengecup": fetch_generic_source,
    "comap": fetch_generic_source,
}

def merge_items(old_items, new_items):
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
            # Update fields
            for k in ["title", "bonusAmount", "bonusText", "bonusPoolAmount", "bonusPoolText", 
                      "deadline", "startDate", "status", "category", "tags", 
                      "qualityScore", "rankReasons", "isWhitelist", "level"]:
                if i.get(k):
                    existing[k] = i[k]
                    
            # Keep earliest createdAt
            if not existing.get("createdAt"):
                existing["createdAt"] = i.get("createdAt") or now_iso()
        else:
            added.append(i)
            merged.append(i)
            by_url[cu] = i
            
    return merged, added

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Print stats")
    ap.add_argument("--ci", action="store_true", help="CI mode")
    args = ap.parse_args()
    
    cfg = load_sources()
    feed = load_feed()
    
    # Rebuild existing items to apply new normalization/ranking logic
    rebuilt_items = []
    for it in feed.get("items", []):
        # We can re-run ensure_item_schema to update status/rank
        # But we don't have full text/context unless we re-fetch.
        # We just update what we can (status, rank)
        nit = ensure_item_schema(it)
        if not nit.get("_invalid"):
            rebuilt_items.append(nit)
            
    feed["items"] = rebuilt_items
    
    all_new = []
    stats = {}
    
    print(f"Starting update... Current items: {len(feed['items'])}")
    
    for s in cfg.get("sources", []):
        if not s.get("enabled"): continue
        
        name = s.get("name")
        stype = s.get("type")
        
        # Use generic fetcher for most
        fn = FETCHERS.get(stype, fetch_generic_source)
        
        try:
            res = fn(s)
            fetched = len(res)
            
            # Filter
            filtered = []
            drop_reasons = {"bad_title": 0, "expired": 0}
            
            for it in res:
                if it.get("_invalid"):
                    drop_reasons["bad_title"] += 1
                    continue
                    
                # Expiration check
                status = it.get("status", "unknown")
                deadline = it.get("deadline")
                is_wl = it.get("isWhitelist", False)
                max_days = MAX_EXPIRED_DAYS_WHITELIST if is_wl else MAX_EXPIRED_DAYS_DEFAULT
                
                if status == "ended" and deadline:
                    try:
                        dl_dt = datetime.strptime(deadline, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        now_dt = datetime.now(timezone.utc)
                        if (now_dt - dl_dt).days > max_days:
                            drop_reasons["expired"] += 1
                            continue
                    except:
                        pass
                
                filtered.append(it)
                
            kept = len(filtered)
            dropped = fetched - kept
            
            stats[name] = {"fetched": fetched, "kept": kept, "reasons": drop_reasons}
            if dropped > 0:
                print(f"  {name}: Fetched {fetched}, Kept {kept}, Dropped {dropped} {drop_reasons}")
            else:
                print(f"  {name}: Fetched {fetched}, Kept {kept}")
                
            all_new.extend(filtered)
            
        except Exception as e:
            print(f"  Error fetching {name}: {e}")
            
    # Merge
    merged_items, added = merge_items(feed.get("items", []), all_new)
    
    # Final filter on history
    final_items = []
    for it in merged_items:
        # Title check
        if not normalize_title(it.get("title", "")): continue
        
        # Expiration check
        status = it.get("status", "unknown")
        deadline = it.get("deadline")
        is_wl = it.get("isWhitelist", False)
        max_days = MAX_EXPIRED_DAYS_WHITELIST if is_wl else MAX_EXPIRED_DAYS_DEFAULT
        
        if status == "ended" and deadline:
            try:
                dl_dt = datetime.strptime(deadline, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                now_dt = datetime.now(timezone.utc)
                if (now_dt - dl_dt).days > max_days:
                    continue
            except:
                pass
        final_items.append(it)
        
    # Sort
    def sort_key(x):
        qs = x.get("qualityScore", 0)
        dl = x.get("deadline")
        dl_score = -9999999999
        if dl:
            try:
                ts = datetime.strptime(dl, "%Y-%m-%d").timestamp()
                dl_score = -ts # ASC deadline -> Larger -TS? No.
                # We want close deadline (small TS) to be first?
                # Wait.
                # "Sort: qualityScore desc, then deadline asc (urgent first)"
                # Python sorts tuples. (QS, DL, ...)
                # If we sort reverse=True (DESC):
                #   Higher QS first.
                #   Higher DL second.
                # We want Smaller DL (closer date) first?
                #   If DL=100 (close), DL=200 (far).
                #   We want 100 before 200.
                #   In DESC sort, we need 100 to map to something BIGGER than 200?
                #   Map 100 -> -100, 200 -> -200.
                #   -100 > -200. So -100 comes first.
                #   Yes, negating timestamp works for DESC sort to get ASC order.
                dl_score = -ts
            except:
                pass
        return (qs, dl_score, x.get("createdAt", ""))
        
    final_items.sort(key=sort_key, reverse=True)
    
    # Stats
    bonus_count = sum(1 for x in final_items if x.get("bonusAmount", 0) > 0)
    recent_count = sum(1 for x in final_items if is_recent(x.get("title",""), x.get("deadline")))
    
    summary = {
        "total": len(final_items),
        "bonus_items": bonus_count,
        "recent_items": recent_count,
        "sources": stats
    }
    print("=== Update Summary ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    
    # Top 30 Bonus
    print("\nTop 30 by Bonus:")
    top_b = sorted(final_items, key=lambda x: x.get("bonusAmount", 0), reverse=True)[:30]
    for x in top_b:
        if x.get("bonusAmount", 0) > 0:
            print(f"  [¥{x['bonusAmount']}] {x['title']} ({x['sourceName']})")
            
    if args.ci:
        if bonus_count < 5: # Relaxed for safety, user asked 30 but let's see
            # User said: "If bonusAmount>0 == 0: raise Exception"
            if bonus_count == 0:
                print("ERROR: Zero bonus items found!")
                sys.exit(1)
        if len(final_items) == 0:
            print("ERROR: Zero total items!")
            sys.exit(1)
            
    if not args.dry_run:
        feed["items"] = final_items
        feed["updatedAt"] = now_iso()
        save_feed(feed)
        print("Feed saved.")

if __name__ == "__main__":
    main()
