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

# Deprecated but kept for compatibility with old update_feed.py references if any
def map_category(title, source_name, summary=""):
    item = {"title": title, "sourceName": source_name, "summary": summary}
    cats, _ = classify_item(item)
    return cats

def ensure_item_schema(item):
    item = dict(item)
    item.setdefault("id", "")
    item.setdefault("title", "")
    item.setdefault("bonusAmount", 0)
    item.setdefault("bonusText", "-")
    item.setdefault("deadline", "")
    item.setdefault("category", [])
    item.setdefault("tags", [])
    item.setdefault("cover", "")
    item.setdefault("sourceName", "")
    item.setdefault("sourceUrl", "")
    item.setdefault("summary", "")
    item.setdefault("createdAt", now_iso())
    item.setdefault("status", "active")
    
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
    deadline = parse_deadline(text)
    if not deadline:
        deadline = item.get("deadline", "")
        
    nd = {
        "id": cid,
        "title": title,
        "bonusAmount": amount,
        "bonusText": bonus_text,
        "deadline": deadline,
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
