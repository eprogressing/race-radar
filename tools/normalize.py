from datetime import datetime, timezone
from dateutil import tz

def iso_dt(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def norm_codeforces(c):
    sid = f"codeforces_{c.get('id')}"
    title = c.get('name') or ""
    start = c.get('startTimeSeconds')
    deadline = iso_dt(start) if isinstance(start, int) else None
    return {
        "id": sid,
        "title": title,
        "deadline": deadline,
        "category": ["编程竞赛"],
        "tags": ["Codeforces"],
        "sourceName": "Codeforces",
        "sourceUrl": f"https://codeforces.com/contests/{c.get('id')}",
        "summary": "Codeforces contest"
    }

def norm_atcoder(c):
    sid = f"atcoder_{c.get('id')}"
    title = c.get('title') or ""
    start = c.get('start_epoch_second')
    deadline = iso_dt(start) if isinstance(start, int) else None
    return {
        "id": sid,
        "title": title,
        "deadline": deadline,
        "category": ["编程竞赛"],
        "tags": ["AtCoder"],
        "sourceName": "AtCoder",
        "sourceUrl": f"https://atcoder.jp/contests/{c.get('id')}",
        "summary": "AtCoder contest"
    }

def norm_drivendata(item):
    sid = f"drivendata_{item.get('slug')}"
    title = item.get('title') or ""
    return {
        "id": sid,
        "title": title,
        "category": ["数据竞赛"],
        "tags": ["DrivenData"],
        "sourceName": "DrivenData",
        "sourceUrl": item.get('url'),
        "summary": "DrivenData competition"
    }

def norm_cumcm(item):
    sid = f"cumcm_{item.get('slug')}"
    title = item.get('title') or ""
    return {
        "id": sid,
        "title": title,
        "category": ["学术竞赛"],
        "tags": ["CUMCM"],
        "sourceName": "CUMCM 官网公告",
        "sourceUrl": item.get('url'),
        "summary": "CUMCM notice"
    }

def norm_challengecup(item):
    sid = f"challengecup_{item.get('slug')}"
    title = item.get('title') or ""
    return {
        "id": sid,
        "title": title,
        "category": ["学术竞赛"],
        "tags": ["挑战杯"],
        "sourceName": "挑战杯通知",
        "sourceUrl": item.get('url'),
        "summary": "挑战杯通知公告"
    }
