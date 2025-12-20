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
    norm_generic, # New generic normalizer
    now_iso,
    canonicalize_url,
    id_from_url,
    extract_bonus,
    extract_bonus_max,
    ensure_item_schema,
    parse_deadline,
    is_recent,
    normalize_title,
    determine_status
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

def rebuild_existing(feed_items):
    rebuilt = []
    for it in feed_items:
        # Check invalid title first
        if not normalize_title(it.get("title", "")):
            continue
            
        # Re-apply schema, classification and ranking
        # Note: we pass a copy to avoid mutating original if needed, but ensure_item_schema returns new dict
        new_it = ensure_item_schema(it)
        if new_it.get("_invalid"):
            continue
            
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
        # Fetch detail for bonus/date/better title
        try:
            # Skip non-html (files)
            if c["url"].endswith((".pdf", ".doc", ".docx", ".zip", ".rar")):
                # Check title normalization for file links too
                if normalize_title(c["title"]):
                    items.append(norm_generic(c, name))
                continue
                
            rd = requests.get(c["url"], timeout=10)
            rd.encoding = rd.apparent_encoding
            sd = BeautifulSoup(rd.text, "lxml")
            
            # Extract main text
            # Try to find main content area
            main_content = ""
            for selector in ["article", "main", ".content", ".detail", ".post", "#content", "#main"]:
                el = sd.select_one(selector)
                if el:
                    main_content = el.get_text(separator="\n", strip=True)
                    break
            if not main_content:
                # Remove footer/nav/script/style from body
                for tag in sd(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                main_content = sd.body.get_text(separator="\n", strip=True) if sd.body else ""
                
            c["text"] = main_content[:5000] # Pass text to normalizer
            
            # Try to extract better title from h1/h2
            h1 = sd.find("h1")
            if h1:
                better_title = h1.get_text(strip=True)
                if normalize_title(better_title):
                    c["title"] = better_title
                    
        except:
            pass
            
        # Normalization and filtering happens in ensure_item_schema called by norm_generic
        item = norm_generic(c, name)
        if not item.get("_invalid"):
            items.append(item)
        
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
            item = norm_generic(item_data, "52竞赛网")
            if not item.get("_invalid"):
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
            item = norm_generic(item_data, "Kaggle")
            if not item.get("_invalid"):
                items.append(item)
            
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
            item = norm_generic(item_data, "赛氪")
            if not item.get("_invalid"):
                items.append(item)
            
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
            for k in ["title", "bonusAmount", "bonusText", "deadline", "startDate", "status", "category", "tags", "qualityScore", "rankReasons", "isWhitelist", "level"]:
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

def enrich_items_with_details(items, sources_cfg):
    src_map = {s["name"]: s for s in sources_cfg}
    candidates = []
    
    # Identify candidates
    for it in items:
        if it.get("bonusAmount", 0) > 0:
            continue
            
        sname = it.get("sourceName")
        if not sname or sname not in src_map:
            continue
            
        cfg = src_map[sname]
        if not cfg.get("detail"):
            continue
            
        # Optimization: prioritize active contests
        if it.get("status") == "ended":
            continue
            
        candidates.append((it, cfg))
        
    by_source = {}
    for it, cfg in candidates:
        sn = cfg["name"]
        if sn not in by_source: by_source[sn] = []
        by_source[sn].append(it)
        
    total_enriched = 0
    total_bonus_found = 0
    
    for sn, its in by_source.items():
        cfg = src_map[sn]
        limit = cfg.get("detail_limit", 30)
        
        # Sort by recency (createdAt)
        its.sort(key=lambda x: x.get("createdAt", ""), reverse=True)
        
        to_fetch = its[:limit]
        print(f"Detail fetching for {sn}: {len(to_fetch)} items (limit {limit})...")
        
        fetched_count = 0
        bonus_count = 0
        
        for item in to_fetch:
            url = item.get("sourceUrl")
            if not url: continue
            
            try:
                r = requests.get(url, timeout=10)
                r.encoding = r.apparent_encoding
                soup = BeautifulSoup(r.text, "lxml")
                
                # Cleanup
                for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
                    tag.decompose()
                    
                # Select content
                selectors = cfg.get("detail_selectors", {})
                content_sel = selectors.get("content")
                
                text = ""
                if content_sel:
                    # Support comma separated selectors
                    for sel in content_sel.split(","):
                        el = soup.select_one(sel.strip())
                        if el:
                            text = el.get_text(separator="\n", strip=True)
                            break
                
                if not text:
                    # Fallback
                    el = soup.select_one("main, article, .content, .detail, .post, #content, #main, .article")
                    if el:
                        text = el.get_text(separator="\n", strip=True)
                    else:
                        text = soup.body.get_text(separator="\n", strip=True) if soup.body else ""
                        
                text = text[:10000]
                
                b_amt, b_txt, p_amt, p_txt = extract_bonus_max(text)
                
                updated = False
                if b_amt > 0:
                    item["bonusAmount"] = b_amt
                    item["bonusText"] = b_txt
                    bonus_count += 1
                    updated = True
                    
                if p_amt > 0:
                    item["bonusPoolAmount"] = p_amt
                    item["bonusPoolText"] = p_txt
                    updated = True
                
                if updated:
                    # Refresh rank
                    item.update(rank_item(item))
                    
                fetched_count += 1
                time.sleep(0.5)
                
            except Exception:
                pass
        
        if fetched_count > 0:
            print(f"  {sn}: Fetched {fetched_count}, Found Bonus {bonus_count}")
            total_enriched += fetched_count
            total_bonus_found += bonus_count
            
    return total_enriched, total_bonus_found

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
            drop_reasons = {"category_mismatch": 0, "expired": 0, "bad_title": 0}
            
            for it in res:
                # 0. Check invalid title
                if it.get("_invalid") or not it.get("title"):
                    drop_reasons["bad_title"] += 1
                    continue
                    
                # 1. Check expiration (soft delete from NEW fetch, not history)
                # Logic: if ended, check if expired too long
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
    
    # Final filter on merged items (to clean up history)
    final_items = []
    dropped_history_count = 0
    for it in merged_items:
        # Check title validity again
        if not normalize_title(it.get("title", "")):
            dropped_history_count += 1
            continue
            
        # Check expiration again
        status = it.get("status", "unknown")
        deadline = it.get("deadline")
        is_wl = it.get("isWhitelist", False)
        max_days = MAX_EXPIRED_DAYS_WHITELIST if is_wl else MAX_EXPIRED_DAYS_DEFAULT
        
        if status == "ended" and deadline:
            try:
                dl_dt = datetime.strptime(deadline, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                now_dt = datetime.now(timezone.utc)
                if (now_dt - dl_dt).days > max_days:
                    dropped_history_count += 1
                    continue
            except:
                pass
        final_items.append(it)
        
    print(f"Dropped {dropped_history_count} items from history due to expiration/bad_title")
    
    # Enrich with details (Bonus)
    enrich_stats = enrich_items_with_details(final_items, cfg.get("sources", []))
    print(f"Enrichment: Fetched {enrich_stats[0]} details, Found {enrich_stats[1]} new bonuses")
    
    if args.ci and enrich_stats[1] == 0:
        print("WARNING: No new bonuses found during enrichment. Check selectors or site changes.")

    # Sort by qualityScore desc, then deadline asc (urgent first), then createdAt desc
    def sort_key(x):
        qs = x.get("qualityScore", 0)
        dl = x.get("deadline")
        
        # For deadline sort:
        # If open/ongoing: urgent (small deadline) is better -> negative deadline?
        # No, we want ASC deadline for open items.
        # But we are sorting reverse=True (DESC) overall.
        # So we need to invert deadline for sorting.
        # Use timestamp inversion.
        dl_score = 0
        if dl:
            try:
                ts = datetime.strptime(dl, "%Y-%m-%d").timestamp()
                # If we want ASC deadline to be higher rank:
                # Closer deadline (smaller TS) -> Higher Rank
                # So we want -TS.
                dl_score = -ts
            except:
                dl_score = -9999999999 # Far future
        else:
            dl_score = -9999999999
            
        return (qs, dl_score, x.get("createdAt", ""))
        
    final_items.sort(key=sort_key, reverse=True)
    
    # Print summary stats
    cat_stats = {"编程":0, "数学建模":0, "AI数据":0, "创新创业":0}
    status_stats = {"upcoming":0, "open":0, "ongoing":0, "ended":0, "unknown":0}
    
    for it in final_items:
        for c in it.get("category", []):
            if c in cat_stats: cat_stats[c] += 1
        st = it.get("status", "unknown")
        if st in status_stats: status_stats[st] += 1
    
    # Top sources stats
    src_stats = {}
    for it in final_items:
        src = it.get("sourceName", "unknown")
        src_stats[src] = src_stats.get(src, 0) + 1
    top_sources = sorted(src_stats.items(), key=lambda x: x[1], reverse=True)[:10]
    
    summary = {
        "total_items": len(final_items),
        "added": added_count,
        "categories": cat_stats,
        "statuses": status_stats,
        "top_sources": dict(top_sources),
        "source_details": stats
    }
    
    print("=== Update Summary ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    
    if args.dry_run or args.ci:
        print("Top 20 items preview:")
        for x in final_items[:20]:
            print(f"  [{x.get('qualityScore')}] {x['title']} ({x.get('status')}|{x.get('deadline')}) - {x.get('rankReasons')}")
            
        print("\nTop 20 by Bonus Amount:")
        top_bonus = sorted(final_items, key=lambda x: x.get("bonusAmount", 0), reverse=True)[:20]
        for x in top_bonus:
            if x.get("bonusAmount", 0) > 0:
                 print(f"  [¥{x['bonusAmount']}] {x['title']} - {x['bonusText']} ({x['sourceName']})")
    
    if args.dry_run:
        print("Dry-run mode: skipping save.")
        sys.exit(0)
        
    # CI mode or normal mode: ALWAYS SAVE if we have items
    # Validation
    if len(final_items) == 0:
        if args.ci:
            print("Error: No items found after merge. CI failed.")
            sys.exit(1)
        else:
            print("Warning: No items found.")
    
    # Update feed
    feed["items"] = final_items
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
