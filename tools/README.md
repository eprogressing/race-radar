# Race Radar Feed Updater

- 本地运行
  - `python3 -m venv .venv`
  - `source .venv/bin/activate`
  - `pip install -r tools/requirements.txt`
  - `python tools/update_feed.py --dry-run`
  - `python tools/update_feed.py`

- 数据源
  - Codeforces API
  - AtCoder contests
  - DrivenData competitions
  - CUMCM 官网公告
  - 挑战杯通知

- 行为
  - 单源失败不影响整体
  - 若无新数据不改写 `feed.json`
  - 合并去重，保留旧数据
