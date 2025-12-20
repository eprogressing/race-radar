# RaceRadar CI 验证指南

## 1. 如何手动触发
1. 进入 GitHub 仓库页面 -> **Actions** 标签页。
2. 在左侧选择 **Update Feed** workflow。
3. 点击右侧的 **Run workflow** 按钮（Branch: main）。

## 2. 验证步骤

### 步骤 A: 检查 Actions 日志
在 workflow 运行完成后，点击 `Run updater (CI mode)` 步骤的日志，确认以下关键信息：

1. **统计摘要 (Update Summary)**:
   - `total_items`: 应该 > 0 (通常 100+)
   - `categories`: 四大类（编程、数学建模、AI数据、创新创业）分布是否合理
   - `dropped`: 检查是否有大量 item 被 drop
     - `bad_title`: 因标题清洗被丢弃的数量（如 "ICP备", "Notice" 等）
     - `expired`: 因过期被丢弃的数量

2. **Top 20 预览**:
   - 日志会打印 `Top 20 items preview:`
   - **排序确认**: 排名靠前的应该是 `status=ongoing` 或 `open`，且 `qualityScore` 较高（>300 或 >200）。
   - **标题确认**: 不应出现“京ICP备”、“2025年...”等纯日期或乱码标题。
   - **状态确认**: Top 20 中不应出现 `ended`（除非它是白名单且刚结束）。

### 步骤 B: 检查 Pages 更新
1. 访问 `https://eprogressing.github.io/race-radar/feed.json` (或对应 Pages 地址)。
2. 检查 `updatedAt` 字段是否为最新时间 (UTC)。
3. 抽查前几条数据的 `rankReasons`，确认包含 "进行中"、"白名单"、"权威来源" 等标签。

## 3. 常见问题排查
- **Item 数为 0**: 检查 fetcher 是否都失败，日志会有 "Error fetching ..."。
- **Top 榜单有过期**: 检查 `update_feed.py` 中的 `MAX_EXPIRED_DAYS` 设置。
- **Git Push 失败**: 可能是并发冲突，Actions 会自动重试（如果配置了 concurrency）或需要手动 re-run。
