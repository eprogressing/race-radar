from datetime import datetime, timezone, timedelta
import hashlib
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import math
import sys
from pathlib import Path

# Fix import path for classify
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
try:
    from tools.classify import classify_item, rank_item
except ImportError:
    # Fallback if tools/classify.py not found or path issue
    def classify_item(item):
        return [], []
    def rank_item(item):
        return {"qualityScore": 0, "rankReasons": [], "isWhitelist": False, "level": "Unknown"}

def iso_dt(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def canonicalize_url(url):
    if not url:
        return ""
    p = urlparse(url)
    scheme = "https"
    netloc = p.netloc
    path = p.path.rstrip("/")
    # filter query, remove utm_* and empty
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in {"spm"}]
    query = urlencode(q, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))

def id_from_url(url):
    cu = canonicalize_url(url)
    h = hashlib.sha1(cu.encode("utf-8")).hexdigest()
    return h[:16]

EXCHANGE_USD_TO_RMB = 7.2

def _parse_cn_number(text):
    # Simple Chinese number parser for common cases
    cn_map = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
        '百': 100, '千': 1000, '万': 10000
    }
    # Handle "五万", "十万", "3万"
    if not text: return None
    
    # Try pure digit first
    m = re.search(r"(\d+(\.\d+)?)", text)
    if m:
        return float(m.group(1))
        
    # Try simple Chinese
    val = 0
    curr = 0
    last_unit = 1
    for char in text:
        if char in cn_map:
            n = cn_map[char]
            if n >= 10:
                if curr == 0: curr = 1
                if n > last_unit:
                    val = (val + curr) * n
                    curr = 0
                    last_unit = n
                else:
                    val += curr * n
                    curr = 0
                    last_unit = n
            else:
                curr = n
    val += curr
    return float(val) if val > 0 else None

def _parse_number(text):
    text = text.replace(",", "").replace("，", "").replace(" ", "")
    # Check for chinese numerals first if no digits
    if not re.search(r"\d", text):
        return _parse_cn_number(text)
        
    m = re.search(r"(\d+(\.\d+)?)", text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except:
        return None

def extract_bonus(text):
    if not text:
        return 0, "-"
    t = text
    # Enhanced patterns
    patterns = [
        # Explicit total bonus
        r"(总奖金|奖池|奖金总额|总奖金池|Total Prize|Prize Pool)[^\\n\\d]{0,10}?([\\d,\\.]+|[一二三四五六七八九十百千万]+)\\s*(万元|万|w|W)",
        r"(总奖金|奖池|奖金总额|总奖金池|Total Prize|Prize Pool)[^\\n\\d]{0,10}?([\\d,\\.]+|[一二三四五六七八九十百千万]+)\\s*(元|RMB|¥)",
        # Top prize
        r"(最高奖|一等奖|金奖|冠军|最高可得|First Prize|Winner|Champion)[^\\n\\d]{0,10}?([\\d,\\.]+|[一二三四五六七八九十百千万]+)\\s*(万元|万|w|W)",
        r"(最高奖|一等奖|金奖|冠军|最高可得|First Prize|Winner|Champion)[^\\n\\d]{0,10}?([\\d,\\.]+|[一二三四五六七八九十百千万]+)\\s*(元|RMB|¥)",
        # Value
        r"(奖品价值|价值)[^\\n\\d]{0,10}?([\\d,\\.]+|[一二三四五六七八九十百千万]+)\\s*(元|RMB|¥)",
        # Simple list: "一等奖：10000元"
        r"(一等奖|二等奖|三等奖)[^\\n\\d：:]*?[：:]\\s*([\\d,\\.]+)\\s*(元|RMB|¥)",
        # USD
        r"(Prize Pool|Total Prize)[^\\n\\d]{0,20}?\\$\\s*([\\d,\\.]+)",
        r"(\$|USD)\\s*([\\d,\\.]+)"
    ]
    
    amount_rmb = 0
    match_text = "-"
    
    for p in patterns:
        m = re.search(p, t, flags=re.IGNORECASE)
        if m:
            # Group index logic varies by pattern
            # General strategy: find the number group and unit group
            groups = m.groups()
            val_str = ""
            unit = ""
            
            # Identify number and unit based on pattern structure
            # Most patterns have: (keyword) ... (number) ... (unit)
            if "$" in p or "USD" in p:
                val_str = groups[-1]
                unit = "USD"
            else:
                # Find the group that looks like a number
                for g in groups:
                    if not g: continue
                    if re.match(r"^[\\d,\\.]+$", g) or re.match(r"^[一二三四五六七八九十百千万]+$", g):
                        val_str = g
                    elif g in ["万元", "万", "w", "W", "元", "RMB", "¥", "USD"]:
                        unit = g
            
            num = _parse_number(val_str)
            if num is None:
                continue
                
            if unit == "USD":
                amount_rmb = int(round(num * EXCHANGE_USD_TO_RMB))
                match_text = f"${num:g} ≈ ¥{amount_rmb/10000:.1f}万" if amount_rmb >= 10000 else f"${num:g} ≈ ¥{amount_rmb}"
            elif unit in ["万元", "万", "w", "W"]:
                amount_rmb = int(round(num * 10000))
                match_text = f"¥{num:g}万"
            else:
                amount_rmb = int(round(num))
                match_text = f"¥{amount_rmb/10000:.1f}万" if amount_rmb >= 10000 else f"¥{amount_rmb}"
            
            # Prefer higher amounts if multiple matches found (greedy check?)
            # For now, break on first high-priority match
            break
            
    return amount_rmb, match_text

def parse_deadline(text):
    if not text:
        return ""
    # Try range patterns first: YYYY.MM.DD-YYYY.MM.DD
    dm = re.findall(r"(\d{4}[.\-年]\d{1,2}[.\-月]\d{1,2})", text)
    if dm:
        # Take the last date as deadline
        last_date = dm[-1].replace(".", "-").replace("年", "-").replace("月", "-").replace("日", "")
        # Ensure YYYY-MM-DD format with zero padding
        parts = last_date.split("-")
        if len(parts) == 3:
            return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    
    # Try relative date: 距离报名截止还有X天
    dm = re.search(r"距离报名截止还有\s*(\d+)\s*天", text)
    if dm:
        days = int(dm.group(1))
        dl = datetime.now() + timedelta(days=days)
        return dl.strftime("%Y-%m-%d")
        
    return ""

def is_recent(text, deadline):
    # If deadline exists, check if it is >= today - 30 days (keep recent history)
    if deadline:
        try:
            dl_dt = datetime.strptime(deadline, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            now_dt = datetime.now(timezone.utc)
            if dl_dt >= (now_dt - timedelta(days=30)):
                return True
        except:
            pass
    
    # If no deadline or invalid, check for current year or last year in text
    current_year = datetime.now().year
    if str(current_year) in text or str(current_year + 1) in text:
        return True
    return False

def normalize_title(title: str):
    if not title:
        return None
        
    # 1. Clean whitespace
    title = re.sub(r'\s+', ' ', title).strip()
    
    # 2. Invalid patterns
    invalid_patterns = [
        r"(京|ICP)备",
        r"版权所有",
        r"联系我们",
        r"隐私政策",
        r"网站地图",
        r"技术支持",
        r"Power by",
        r"All Rights Reserved",
    ]
    for p in invalid_patterns:
        if re.search(p, title, re.IGNORECASE):
            return None
            
    # 3. Date-only title check
    # Matches "2025年3月21日2025年3月25日" or similar
    if re.match(r"^[\d\s年\.月日:-]+$", title):
        return None
        
    # 4. Length check
    if len(title) < 4: # Relaxed slightly from 6
        return None
        
    # 5. Pure "Notice" check
    # If title contains only "Notice/News", drop unless it has contest keywords
    # Keywords: 大赛, 竞赛, 挑战赛, 杯, 赛, Contest, Challenge, 选拔
    contest_keywords = [
        "大赛", "竞赛", "挑战赛", "杯", "赛", "Contest", "Challenge", "选拔", "Olympic", "Hackathon"
    ]
    notice_keywords = ["通知", "公告", "新闻", "Notice", "News", "Announcement"]
    
    is_notice = any(k in title for k in notice_keywords)
    has_contest = any(k in title for k in contest_keywords)
    
    if is_notice and not has_contest:
        return None
        
    # If it's a valid title, return cleaned version
    return title

def determine_status(start_date, deadline):
    """
    Returns: upcoming, open, ongoing, ended, unknown
    """
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    
    dl_dt = None
    start_dt = None
    
    if deadline:
        try:
            dl_dt = datetime.strptime(deadline, "%Y-%m-%d")
        except:
            pass
            
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        except:
            pass
            
    # 1. Ended
    if dl_dt and dl_dt < now:
        # Check if it's "today" (ended today implies ended usually?)
        # Let's say deadline is inclusive. So if now > deadline + 1 day?
        # Standard: deadline is end of day.
        # Simple: if deadline date < today date -> ended
        if deadline < today_str:
            return "ended"
            
    # 2. Upcoming
    if start_dt and start_dt > now:
        return "upcoming"
        
    # 3. Ongoing (Started but not ended)
    if start_dt and dl_dt:
        if start_dt <= now <= dl_dt:
            return "ongoing"
            
    # 4. Open (Has deadline, not ended, start unknown or passed)
    if dl_dt and dl_dt >= now:
        return "open"
        
    # 5. Unknown
    return "unknown"

def parse_date_range(text):
    """
    Extract startDate and deadline from text like "2025年3月21日-2025年3月25日"
    """
    if not text:
        return None, None
        
    # Try range pattern
    # 2025.03.21-2025.03.25
    # 2025年3月21日-3月25日
    range_patterns = [
        r"(\d{4}[.\-年]\d{1,2}[.\-月]\d{1,2})[日\s]*[-~至][\s]*(\d{4}[.\-年]\d{1,2}[.\-月]\d{1,2})",
        # Simplified second part not fully supported yet for safety, assume full dates usually
    ]
    
    for p in range_patterns:
        m = re.search(p, text)
        if m:
            d1 = m.group(1).replace(".", "-").replace("年", "-").replace("月", "-").replace("日", "")
            d2 = m.group(2).replace(".", "-").replace("年", "-").replace("月", "-").replace("日", "")
            
            # Format to YYYY-MM-DD
            def fmt(d):
                parts = d.split("-")
                if len(parts) == 3:
                    return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                return None
            
            return fmt(d1), fmt(d2)
            
    # Fallback: find single dates
    dates = re.findall(r"(\d{4}[.\-年]\d{1,2}[.\-月]\d{1,2})", text)
    valid_dates = []
    for d in dates:
        d_clean = d.replace(".", "-").replace("年", "-").replace("月", "-").replace("日", "")
        parts = d_clean.split("-")
        if len(parts) == 3:
            valid_dates.append(f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}")
            
    if not valid_dates:
        return None, None
        
    # Heuristic: if multiple dates, last one is usually deadline
    # If context implies "start": not handled deeply here, relying on simple range
    return None, valid_dates[-1]

def ensure_item_schema(item):
    item = dict(item)
    
    # Clean Title First
    clean_title = normalize_title(item.get("title", ""))
    if not clean_title:
        # Mark as invalid for caller to drop
        item["_invalid"] = True
        return item
    item["title"] = clean_title
    
    item.setdefault("id", "")
    item.setdefault("bonusAmount", 0)
    item.setdefault("bonusText", "-")
    item.setdefault("category", [])
    item.setdefault("tags", [])
    item.setdefault("cover", "")
    item.setdefault("sourceName", "")
    item.setdefault("sourceUrl", "")
    item.setdefault("summary", "")
    item.setdefault("createdAt", now_iso())
    
    # Date & Status Logic
    text = item.get("text", "") or item.get("summary", "")
    start, end = parse_date_range(text)
    
    # Prefer existing specific fields if source provided them
    if not item.get("startDate") and start:
        item["startDate"] = start
    if not item.get("deadline") and end:
        item["deadline"] = end
        
    # If no deadline yet, try legacy parse
    if not item.get("deadline"):
        item["deadline"] = parse_deadline(text)
        
    item["status"] = determine_status(item.get("startDate"), item.get("deadline"))
    
    # 1. Classify & Tag
    cats, tags = classify_item(item)
    
    # Merge existing categories if any (e.g. fixed from source)
    existing_cats = item.get("category", [])
    final_cats = list(set(existing_cats + cats))
    # Enforce 4 classes
    valid_cats = [c for c in final_cats if c in ["编程","数学建模","AI数据","创新创业"]]
    item["category"] = valid_cats
    
    # Merge tags
    existing_tags = item.get("tags", [])
    item["tags"] = list(set(existing_tags + tags))
    
    # 2. Rank
    rank_info = rank_item(item)
    item.update(rank_info)
    
    return item

# Legacy support for specific sources
def norm_codeforces(c):
    title = c.get('name') or ""
    start = c.get('startTimeSeconds')
    deadline = iso_dt(start) if isinstance(start, int) else ""
    url = f"https://codeforces.com/contests/{c.get('id')}"
    cid = id_from_url(url)
    item = {
        "id": cid,
        "title": title,
        "bonusAmount": 0,
        "bonusText": "-",
        "deadline": deadline,
        "category": ["编程"],
        "tags": ["Codeforces"],
        "cover": "",
        "sourceName": "Codeforces",
        "sourceUrl": canonicalize_url(url),
        "summary": "Codeforces contest",
        "createdAt": now_iso()
    }
    return ensure_item_schema(item)

def norm_atcoder(c):
    title = c.get('title') or ""
    start = c.get('start_epoch_second')
    deadline = iso_dt(start) if isinstance(start, int) else ""
    url = f"https://atcoder.jp/contests/{c.get('id')}"
    cid = id_from_url(url)
    item = {
        "id": cid,
        "title": title,
        "bonusAmount": 0,
        "bonusText": "-",
        "deadline": deadline,
        "category": ["编程"],
        "tags": ["AtCoder"],
        "cover": "",
        "sourceName": "AtCoder",
        "sourceUrl": canonicalize_url(url),
        "summary": "AtCoder contest",
        "createdAt": now_iso()
    }
    return ensure_item_schema(item)

def norm_drivendata(item):
    url = item.get('url')
    title = item.get('title') or ""
    cid = id_from_url(url)
    cat = ["AI数据"]
    amount, bonus_text = extract_bonus(item.get('text', "") or "")
    nd = {
        "id": cid,
        "title": title,
        "bonusAmount": amount,
        "bonusText": bonus_text,
        "deadline": item.get("deadline", "") or "",
        "category": cat,
        "tags": ["DrivenData"],
        "cover": "",
        "sourceName": "DrivenData",
        "sourceUrl": canonicalize_url(url),
        "summary": item.get('summary', "") or "DrivenData competition",
        "createdAt": now_iso()
    }
    return ensure_item_schema(nd)

def norm_generic(item, source_name=""):
    """
    Generic normalization for sources that provide raw dicts
    """
    url = item.get('url')
    title = item.get('title') or ""
    cid = id_from_url(url)
    text = item.get('text', "") or ""
    
    amount, bonus_text = extract_bonus(text)
    
    # deadline parsing is handled in ensure_item_schema if not provided
    # but we can try here to pass it explicitly
    deadline = item.get("deadline", "")
        
    nd = {
        "id": cid,
        "title": title,
        "bonusAmount": amount,
        "bonusText": bonus_text,
        "deadline": deadline,
        "text": text, # Pass full text for parsing
        "category": item.get("category", []), # Will be augmented by ensure_item_schema
        "tags": [],
        "cover": "",
        "sourceName": source_name,
        "sourceUrl": canonicalize_url(url),
        "summary": item.get('summary', "") or title,
        "createdAt": now_iso()
    }
    return ensure_item_schema(nd)

# Re-export for compatibility
norm_cumcm = lambda x: norm_generic(x, "CUMCM 官网公告")
norm_challengecup = lambda x: norm_generic(x, "挑战杯通知")
