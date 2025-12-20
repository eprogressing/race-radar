import re
import yaml
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
WHITELIST_PATH = ROOT / "tools" / "whitelist.yaml"

_WHITELIST_CACHE = None

def load_whitelist():
    global _WHITELIST_CACHE
    if _WHITELIST_CACHE:
        return _WHITELIST_CACHE
    try:
        with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
            _WHITELIST_CACHE = yaml.safe_load(f)
    except:
        _WHITELIST_CACHE = {"whitelist": [], "official_domains": []}
    return _WHITELIST_CACHE

def classify_item(item):
    """
    Input: item dict (title, summary, sourceName, sourceUrl)
    Output: (categories: list, tags: list)
    """
    text = (item.get("title", "") + " " + item.get("summary", "") + " " + item.get("sourceName", "")).lower()
    
    cats = set()
    tags = set()
    
    # 1. Category Classification
    # 数学建模
    if any(k in text for k in ["数学建模", "建模", "mcm", "icm", "美赛", "国赛", "华为杯", "统计建模", "cumcm", "comap", "mathorcup"]):
        cats.add("数学建模")
    
    # 编程
    if any(k in text for k in ["icpc", "acm", "ccpc", "程序设计", "蓝桥杯", "codeforces", "atcoder", "操作系统", "编译", "nscscc", "龙芯杯", "编程", "算法", "hackathon", "leetcode"]):
        cats.add("编程")
        
    # AI数据
    if any(k in text for k in ["算法", "数据", "ai", "人工智能", "机器学习", "深度学习", "aiops", "天池", "kaggle", "drivendata", "大模型", "cv", "nlp", "llm"]):
        cats.add("AI数据")
        
    # 创新创业
    if any(k in text for k in ["挑战杯", "互联网+", "创新创业", "创业", "商业计划书", "路演", "独角兽", "创青春", "business plan"]):
        cats.add("创新创业")
        
    # Fallback / Priority
    final_cats = list(cats)
    # Heuristic priority if multiple
    if "编程" in cats: final_cats = ["编程"]
    elif "数学建模" in cats: final_cats = ["数学建模"]
    elif "AI数据" in cats: final_cats = ["AI数据"]
    elif "创新创业" in cats: final_cats = ["创新创业"]
    
    # 2. Tag Generation
    wl = load_whitelist()
    
    # Whitelist tags
    for rule in wl.get("whitelist", []):
        if re.search(rule["pattern"], text, re.IGNORECASE):
            if rule.get("level") == "National":
                tags.add("国家级")
            elif rule.get("level") == "International":
                tags.add("国际级")
    
    # Attribute tags
    if "高校" in text or "大学" in text: tags.add("高校")
    if "团队" in text: tags.add("团队赛")
    if "本科" in text: tags.add("本科生")
    if "研究生" in text: tags.add("研究生")
    if "开源" in text: tags.add("开源")
    if item.get("bonusAmount", 0) > 0: tags.add("有奖金")
    if "证书" in text: tags.add("证书")
    if item.get("status") == "ongoing": tags.add("进行中")
    if item.get("status") == "open": tags.add("报名中")
    
    return final_cats, list(tags)

def rank_item(item):
    """
    Calculate qualityScore, rankReasons, isWhitelist, level
    """
    wl = load_whitelist()
    text = (item.get("title", "") + " " + item.get("summary", "") + " " + item.get("sourceName", "")).lower()
    url = (item.get("sourceUrl", "")).lower()
    
    score = 0
    reasons = []
    level = "Unknown"
    is_whitelist = False
    
    # 1. Whitelist Check (Base Weight)
    for rule in wl.get("whitelist", []):
        if re.search(rule["pattern"], text, re.IGNORECASE):
            score += 200 # Major boost
            is_whitelist = True
            level = rule.get("level", "Unknown")
            reasons.append(f"白名单:{rule['pattern']}")
            if level == "National":
                score += 100
                reasons.append("国家级")
            break
            
    # 2. Status Weight (Time Criticality)
    status = item.get("status", "unknown")
    if status in ["ongoing", "open"]:
        score += 300
        reasons.append("进行中/报名中")
    elif status == "upcoming":
        # Check if starting soon
        start = item.get("startDate")
        if start:
            try:
                start_dt = datetime.strptime(start, "%Y-%m-%d")
                days_to_start = (start_dt - datetime.now()).days
                if days_to_start <= 14:
                    score += 260
                    reasons.append("即将开始")
                else:
                    score += 120
            except:
                score += 120
        else:
            score += 120
    elif status == "unknown":
        score += 50
    elif status == "ended":
        score -= 500
        
    # 3. Deadline Urgency (for open/ongoing)
    if status in ["open", "ongoing"]:
        deadline = item.get("deadline")
        if deadline:
            try:
                dl_dt = datetime.strptime(deadline, "%Y-%m-%d")
                days_left = (dl_dt - datetime.now()).days
                if 0 <= days_left <= 3:
                    score += 120
                    reasons.append("即将截止")
                elif 0 <= days_left <= 7:
                    score += 80
                    reasons.append("一周内截止")
                elif 0 <= days_left <= 30:
                    score += 30
            except:
                pass

    # 4. Source Authority
    src_name = item.get("sourceName", "")
    high_auth_sources = ["CUMCM", "COMAP", "NSCSCC", "蓝桥杯", "挑战杯", "天池", "阿里云", "Kaggle", "DrivenData"]
    if any(s in src_name for s in high_auth_sources):
        score += 120
        reasons.append("权威来源")
    elif src_name in ["赛氪", "52竞赛网"]:
        score += 60
    elif src_name in ["Codeforces", "AtCoder"]:
        score += 10 # Regular contests
        
    for domain in wl.get("official_domains", []):
        if domain in url and "权威来源" not in reasons:
            score += 20
            reasons.append("官方来源")
            break
            
    # 5. Bonus Weight
    bonus = item.get("bonusAmount", 0)
    if bonus >= 100000:
        score += 80
        reasons.append("超高奖金")
    elif bonus >= 50000:
        score += 60
        reasons.append("高奖金")
    elif bonus >= 10000:
        score += 40
    elif bonus >= 5000:
        score += 20
        
    # 6. Category Preference
    cats = item.get("category", [])
    if any(c in ["编程", "数学建模", "AI数据", "创新创业"] for c in cats):
        score += 10
        
    return {
        "qualityScore": score,
        "rankReasons": reasons[:3], # Keep top 3 reasons
        "isWhitelist": is_whitelist,
        "level": level
    }
