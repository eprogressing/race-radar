import re
import yaml
from pathlib import Path

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
    
    # 1. Whitelist Check
    for rule in wl.get("whitelist", []):
        if re.search(rule["pattern"], text, re.IGNORECASE):
            w = rule.get("weight", 0)
            score += w
            is_whitelist = True
            level = rule.get("level", "Unknown")
            reasons.append(f"白名单:{rule['pattern']}")
            break # Match once
            
    # 2. Official Domain Check
    for domain in wl.get("official_domains", []):
        if domain in url:
            score += 20
            reasons.append("官方来源")
            break
            
    # 3. Bonus Weight
    bonus = item.get("bonusAmount", 0)
    if bonus >= 100000:
        score += 25
        reasons.append("高奖金")
    elif bonus >= 50000:
        score += 18
        reasons.append("奖金丰厚")
    elif bonus >= 10000:
        score += 12
    elif bonus >= 5000:
        score += 7
        
    # 4. Deadline Weight (handled dynamically in update_feed, but static part here)
    # 5. Category Preference
    cats = item.get("category", [])
    if any(c in ["编程", "数学建模", "AI数据", "创新创业"] for c in cats):
        score += 5
        
    return {
        "qualityScore": score,
        "rankReasons": reasons,
        "isWhitelist": is_whitelist,
        "level": level
    }
