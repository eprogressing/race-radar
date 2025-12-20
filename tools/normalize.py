from datetime import datetime, timezone, timedelta
import hashlib
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import math

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

def _parse_number(text):
    text = text.replace(",", "").replace("，", "").replace(" ", "")
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
    # High priority patterns
    patterns = [
        r"(总奖金|奖池|奖金总额|总奖金池)[^\\n\\d]{0,10}?([\\d,\\.]+)\\s*(万元|万|w|W)",
        r"(总奖金|奖池|奖金总额|总奖金池)[^\\n\\d]{0,10}?([\\d,\\.]+)\\s*(元|RMB|¥)",
        r"(最高奖|一等奖|金奖|冠军|最高可得)[^\\n\\d]{0,10}?([\\d,\\.]+)\\s*(万元|万|w|W)",
        r"(最高奖|一等奖|金奖|冠军|最高可得)[^\\n\\d]{0,10}?([\\d,\\.]+)\\s*(元|RMB|¥)",
        r"(Prize Pool|Total Prize)[^\\n\\d]{0,20}?\\$\\s*([\\d,\\.]+)",
        r"(First Prize|Winner|Champion)[^\\n\\d]{0,20}?\\$\\s*([\\d,\\.]+)",
        r"(\$|USD)\\s*([\\d,\\.]+)"
    ]
    
    amount_rmb = 0
    match_text = "-"
    
    for p in patterns:
        m = re.search(p, t, flags=re.IGNORECASE)
        if m:
            val_str = m.group(2) if len(m.groups()) >= 2 else ""
            unit = m.group(3) if len(m.groups()) >= 3 else ""
            
            # Special case for USD patterns
            if "$" in p or "USD" in p:
                val_str = m.group(len(m.groups())) # Last group is number
                unit = "USD"
            
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
    # If deadline exists, check if it is >= today - 7 days
    if deadline:
        try:
            dl_dt = datetime.strptime(deadline, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            now_dt = datetime.now(timezone.utc)
            if dl_dt >= (now_dt - timedelta(days=7)):
                return True
        except:
            pass
    
    # If no deadline or invalid, check for current year or last year in text
    current_year = datetime.now().year
    if str(current_year) in text or str(current_year + 1) in text:
        return True
    return False

def calculate_quality_score(item):
    score = 0
    
    # 1. Bonus amount
    bonus = item.get("bonusAmount", 0)
    if bonus > 0:
        # log(1+bonus) * 80 -> 1万~320, 10万~400, 100万~480
        score += math.log(1 + bonus) * 15 # slightly tuned down to balance
        if bonus >= 10000: score += 40
        if bonus >= 100000: score += 60
        
    # 2. Deadline urgency
    deadline = item.get("deadline")
    if deadline:
        try:
            dl_dt = datetime.strptime(deadline, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            now_dt = datetime.now(timezone.utc)
            days_left = (dl_dt - now_dt).days
            
            if days_left < 0:
                score -= 300 # Expired
            elif days_left <= 7:
                score += 120 # Very urgent
            elif days_left <= 30:
                score += 60 # Urgent
            elif days_left <= 90:
                score += 20
        except:
            pass
            
    # 3. Source weight
    src = item.get("sourceName", "")
    if "赛氪" in src: score += 120
    elif "52竞赛网" in src: score += 100
    elif "Kaggle" in src: score += 20
    elif "Codeforces" in src or "AtCoder" in src: score += 80 # High quality coding platforms
    
    # 4. Keywords
    text = (item.get("title", "") + item.get("summary", "")).lower()
    
    # Authority keywords
    if any(k in text for k in ["教育部", "工信部", "团中央", "国赛", "全国", "国际", "顶级", "权威", "官方", "ACM", "ICPC", "CCPC"]):
        score += 80
        
    # Domain keywords
    if any(k in text for k in ["ai", "人工智能", "大数据", "算法", "建模", "创业", "创新", "robot", "program"]):
        score += 40
        
    return int(score)

def map_category(title, source_name, summary=""):
    t = (title or "") + " " + (source_name or "") + " " + (summary or "")
    t = t.lower()
    cats = []
    
    if any(k in t for k in ["codeforces", "atcoder", "icpc", "ccpc", "程序设计", "算法", "软件杯", "蓝桥杯", "编程", "acm", "hackathon", "黑客松", "leetcode"]):
        cats.append("编程")
        
    if any(k in t for k in ["数学建模", "美赛", "mcm", "icm", "建模", "cumcm", "comap", "国赛", "研赛", "mathorcup", "华中杯", "五一建模"]):
        cats.append("数学建模")
        
    if any(k in t for k in ["kaggle", "drivendata", "ai", "人工智能", "机器学习", "深度学习", "数据", "大模型", "算法挑战赛", "开悟", "计算机视觉", "nlp", "cv", "llm"]):
        cats.append("AI数据")
        
    if any(k in t for k in ["挑战杯", "互联网+", "创业", "创新创业", "创青春", "商业计划书", "创业大赛"]):
        cats.append("创新创业")
        
    # Unique strict mapping
    if cats:
        # Priority: 编程 > 数学建模 > AI数据 > 创新创业 (heuristic)
        if "编程" in cats: return ["编程"]
        if "数学建模" in cats: return ["数学建模"]
        if "AI数据" in cats: return ["AI数据"]
        return ["创新创业"]
        
    return []

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
    
    # Calculate scores
    qs = calculate_quality_score(item)
    item["qualityScore"] = qs
    item["isHighQuality"] = qs >= 400
    
    return item

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

def norm_cumcm(item):
    url = item.get('url')
    title = item.get('title') or ""
    cid = id_from_url(url)
    amount, bonus_text = extract_bonus(item.get('text', "") or "")
    nd = {
        "id": cid,
        "title": title,
        "bonusAmount": amount,
        "bonusText": bonus_text,
        "deadline": item.get("deadline", "") or "",
        "category": ["数学建模"],
        "tags": ["CUMCM"],
        "cover": "",
        "sourceName": "CUMCM 官网公告",
        "sourceUrl": canonicalize_url(url),
        "summary": item.get('summary', "") or "CUMCM notice",
        "createdAt": now_iso()
    }
    return ensure_item_schema(nd)

def norm_challengecup(item):
    url = item.get('url')
    title = item.get('title') or ""
    cid = id_from_url(url)
    amount, bonus_text = extract_bonus(item.get('text', "") or "")
    nd = {
        "id": cid,
        "title": title,
        "bonusAmount": amount,
        "bonusText": bonus_text,
        "deadline": item.get("deadline", "") or "",
        "category": ["创新创业"],
        "tags": ["挑战杯"],
        "cover": "",
        "sourceName": "挑战杯通知",
        "sourceUrl": canonicalize_url(url),
        "summary": item.get('summary', "") or "挑战杯通知公告",
        "createdAt": now_iso()
    }
    return ensure_item_schema(nd)
