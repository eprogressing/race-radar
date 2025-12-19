from datetime import datetime, timezone
import hashlib
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

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
    patterns = [
        r"(总奖金|奖池|奖金|奖励)[^\\n]{0,20}?([\\d,\\.]+)\\s*(万元|万|元|人民币|RMB|¥)",
        r"(一等奖|最高可得|最高奖)[^\\n]{0,20}?([\\d,\\.]+)\\s*(万元|万|元|人民币|RMB|¥)",
        r"(Prize|Prizes|Award)[^\\n]{0,40}?\\$\\s*([\\d,\\.]+)",
        r"(USD)\\s*([\\d,\\.]+)"
    ]
    amount_rmb = 0
    match_text = None
    for p in patterns:
        m = re.search(p, t, flags=re.IGNORECASE)
        if m:
            match_text = m.group(0)
            # detect currency/unit
            if "$" in m.group(0) or m.group(1).upper() == "USD":
                val = _parse_number(m.group(2))
                if val is not None:
                    amount_rmb = int(round(val * EXCHANGE_USD_TO_RMB))
            else:
                # RMB units, detect 万
                # find number in group2
                num = _parse_number(m.group(2))
                unit = m.group(3) if len(m.groups()) >= 3 else ""
                if num is not None:
                    if unit and ("万" in unit):
                        amount_rmb = int(round(num * 10000))
                    else:
                        amount_rmb = int(round(num))
            break
    if amount_rmb <= 0:
        return 0, "-"
    return amount_rmb, match_text or "-"

def map_category(title, source_name):
    t = (title or "") + " " + (source_name or "")
    if any(k in t for k in ["Codeforces", "AtCoder", "编程", "算法", "ACM", "蓝桥", "程序"]):
        return ["编程"]
    if any(k in t for k in ["数学建模", "美赛", "MCM", "ICM", "建模", "CUMCM", "COMAP"]):
        return ["数学建模"]
    if any(k in t for k in ["Kaggle", "DrivenData", "AI", "机器学习", "数据"]):
        return ["AI数据"]
    if any(k in t for k in ["挑战杯", "互联网+", "创业", "创新创业"]):
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
