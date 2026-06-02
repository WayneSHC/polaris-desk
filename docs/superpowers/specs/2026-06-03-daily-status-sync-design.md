# Daily Status Sync — 設計規格

- 日期：2026-06-03
- 狀態：Draft（待 PM/團隊 review）
- 對應需求：每個角色的 daily task 狀態自動匯整到 GitHub，供 R1 PM 每日掌握進度、管理專案、再更新到 Notion

## 1. 目標與非目標

### 目標
- 每日**自動**產生「各角色昨日進度」摘要，零回報摩擦（不要求任何人手動填寫）。
- 進度資料**自動推導自 GitHub 活動**（PR / commit / review / issue）。
- R1 PM 每日早上可直接讀到摘要，並取得 **Notion 可匯入的 CSV** 更新 Notion 進度資料庫。
- 沿用既有工具鏈：`uv` + Python 3.13 + Makefile + pytest + ruff；同 repo 內建 `GITHUB_TOKEN`，**不需額外金鑰**。

### 非目標（YAGNI）
- 不自動直送 Notion API（方案 3，列為未來升級；本版只到 CSV）。
- 不抓「沒碰到 GitHub 的工作」（開會、讀文件研究、未 commit 的手動 GCP 操作）。此為已知取捨，見 §7。
- 不做 Slack/LINE 通知（GitHub Issue 的內建通知已足夠）。

## 2. 已知取捨（白紙黑字）

「自動推導」只看得到**碰到 GitHub 的事**：PR（開啟 / 合併）、commit、PR review、issue（開啟 / 關閉）。
純規劃、研究、會議、未經 commit 的手動操作不會出現。

對策（**預設零摩擦，不強迫**）：角色若想讓非程式工作現身，可在當日 Status Issue 留言，或在 PR 描述加一行 `status: <一句話>`。本版只保留這個「後門」慣例，不另外實作解析（未來可加）。

## 3. 架構與資料流

```
每天 07:10(台北) ── cron ──▶ GitHub Action (daily-status.yml)
   │
   ├─ fetch   抓「台北昨日 00:00–24:00」全 repo 活動（GitHub REST API + GITHUB_TOKEN）
   ├─ aggregate  依 author → 角色 分組（roles 對照表）
   ├─ render  產生 ① Markdown 摘要 ② Notion 用 CSV
   └─ publish
        ├─ 更新「📊 Daily Status (rolling)」單一 Issue（label=daily-status；
        │   把今日區塊 prepend 到 body 最上方，每日一個 <details> 收合區）
        └─ 把 .md + .csv commit 到 `status` 分支（穩定 raw 連結 + 歷史）
   ▼
R1 PM 早上收到 Issue 通知 → 點 status 分支的 CSV raw 連結 → 匯進 Notion 進度資料庫
```

設計原則：把 **aggregate / render 寫成純函式（不碰網路）**，`fetch` 與 `publish` 是唯二有副作用的元件，邏輯可完整單元測試。

## 4. 元件（檔案結構）

> **採用 repo 既有 src layout**（`pyproject.toml`：`pythonpath=["src"]`、`packages=["src/polaris"]`、測試 `from polaris...`），故程式放 `src/polaris/daily_status/`（**不是** `scripts/`，否則 pytest 無法 import）。

```
src/polaris/daily_status/
  __init__.py
  roles.py       # username → 角色(R1–R7)+姓名 對照表（唯一事實來源）
  timewindow.py  # 計算 Asia/Taipei「昨日」起訖（回傳 UTC 區間）
  fetch.py       # 對外 I/O：呼叫 GitHub API 抓活動（HTTP client 可注入 → 好測）
  aggregate.py   # 純函式：events → 每角色 digest dataclass
  render.py      # 純函式：digest → markdown / csv / 滾動 body 合併
  publish.py     # 對外 I/O：找 / 更新 / 建立滾動 Issue（HTTP client 可注入）
  __main__.py    # CLI 入口：python -m polaris.daily_status；fetch→aggregate→render→寫檔(+--post-issue)；--dry-run
.github/workflows/daily-status.yml   # cron 排程 + 最小權限；跑 CLI 後把產出 commit 到 status 分支
Makefile                              # 新增 daily-status / daily-status-dry 兩個 target
tests/test_daily_status.py            # roles / timewindow / aggregate / render / publish 單元測試
```

各元件職責（介面清楚、可獨立理解測試）：

| 元件 | 做什麼 | 輸入 → 輸出 | 副作用 |
|---|---|---|---|
| `roles.py` | 帳號歸角色 | username → `Role(code, name)` 或 None | 無 |
| `timewindow.py` | 算昨日窗 | 今日(台北 date) → (start_utc, end_utc) | 無 |
| `fetch.py` | 抓活動 | (repo, 時間窗, client) → `list[Event]` | 網路 |
| `aggregate.py` | 分組統計 | `list[Event]` → `DailyDigest` | 無 |
| `render.py` | 產出格式 + 合併滾動 body | `DailyDigest` → md / csv；`(舊body, 今日block)` → 新body | 無 |
| `publish.py` | 找 / 更新 / 建立滾動 Issue | `(client, body)` → issue number | 網路 |
| `__main__.py` | 串接 + 寫檔 + 發 Issue | CLI args | 網路 + 寫檔 |

> **相依限制（重要）**：`daily_status` 子套件**只依賴 Python 標準函式庫**（`urllib` / `json` / `csv` / `zoneinfo` / `dataclasses` / `argparse`）。如此 Action 不必安裝 langgraph/google 等重相依，直接 `PYTHONPATH=src python -m polaris.daily_status` 即可跑（快、穩）。`status` 分支的 git commit/push 由 workflow yaml 負責（不放進 Python）。

## 5. 資料定義

### 5.1 抓取的活動（每位作者）
- merged PR（**完成的 task 主訊號**）：number / title / merged_at
- 開啟中的 PR（進行中）：number / title
- 給出的 PR review 數
- 關閉的 issue：number / title
- commit 數（當日窗內）— 次要訊號；因採 squash merge，commit 歸屬可能集中在合併者，故以 **merged PR 為主、commit 數為輔**

### 5.2 角色對照（`roles.py` 初值，動工前以 `gh api` 逐一驗證真實存在）
| 角色 | 姓名 | GitHub username |
|---|---|---|
| R1 PM | 郝家銘 | `hbb97tw-netizen` |
| R2 AI 架構師 | 施惠棋 | `WayneSHC`（owner） |
| R3 Agent 工程師 | 謝劼恩 | `officehsieh-afk` |
| R4 資料工程師 | 吳瑾瑜 | `holajennytw` |
| R5 Eval Lead | 楊宗勲 | `Arronyang0416` |
| R6 金融品質工程師 | 黃俊維 | `aa851115tw-tech` |
| R7 Demo 與全端 | 李靜雲 | `angelali2026888-blip` |

> 註：每人同時是某角色「主」＋另一角色「次」。本表以 **GitHub 帳號 → 主角色** 一對一對應；活動一律歸主角色（PM 若要看備援視角可在 Notion 自行加欄）。

### 5.3 CSV 輸出（每天一檔，每角色一列）
對齊既有 `Notion 匯入_*.csv` 風格（中文欄名、UTF-8、role code）：

```
日期,角色,成員,完成PR,進行中PR,Review數,關閉Issue,commit數,摘要
2026-06-03,R1,郝家銘,1,0,2,0,3,"合併 #42 站會看板；review #41,#43"
...（R2–R7 各一列）
```
PM 每日匯入 → Notion 累積成「角色 × 日期」進度表（4 週約 28×7 列）。

### 5.4 Issue 輸出（單一滾動 Issue）
- 採**一張固定的滾動 Issue**（不每天開新的），維持單一 bookmark、issue 列表乾淨。
- 標題：`📊 Daily Status (rolling)`
- label：`daily-status`
- 每日內容：把今日區塊（標題 `YYYY-MM-DD (Asia/Taipei)` + 每角色條列 + 總表）以一個 `<details>` 收合區 **prepend 到 body 最上方**（最新在上），footer 固定一行「自動產生，僅涵蓋 GitHub 活動」。
- 識別方式：以 label=`daily-status` 搜尋既有滾動 Issue；找到就更新 body，找不到就建立。
- 長度防護：body 只保留**最近 14 天**內聯，更早的日期移除並在底部明示「更早請見 `status` 分支 `reports/daily/`」（避免靜默截斷；完整歷史永遠在 status 分支）。

## 6. 排程與時區
- cron：`10 23 * * *`（UTC）= **台北 07:10**
- 報告窗：以 `Asia/Taipei` 計算「昨日 00:00–24:00」，於 `timewindow.py` 處理，避免 UTC 跨日錯位（單元測試鎖定，含跨月邊界）。
- 每日皆跑（4 週衝刺含週末）。

## 7. 錯誤處理（不靜默漏掉）
- **未對應角色的帳號**（bot / 用別帳號的隊友）→ 歸到摘要的「未對應帳號」區塊並列出，PM 一看就知道要補 `roles.py`，絕不丟棄。
- **當日零活動** → 仍發 Issue 並寫「今日無 GitHub 活動」，讓「沒進度」明示化。
- **API / 發佈失敗** → Action 直接紅燈失敗（Actions 頁可見），不發半殘 Issue、不寫半殘 CSV。
- **`status` 分支不存在** → 首次執行自動以 orphan 方式建立。

## 8. 權限與安全
- workflow 宣告最小權限：`permissions: { contents: write, issues: write }`，用內建 `GITHUB_TOKEN`，**不引入任何 PAT / secret**。
- 寫檔走未受保護的 `status` 分支，不碰 `main`（避開 branch protection：require PR + 1 approval + linear history）。
- 不輸出任何金鑰 / email 以外的 PII；CSV 只含公開的 GitHub 活動與姓名（姓名已於團隊內部文件公開）。

## 9. 測試策略
- 純函式全上 pytest：`aggregate`（餵假 events 比對 digest）、`render`（digest → 預期 md/csv 片段）、`timewindow`（含跨月 / 月底邊界）、`roles`（已知 / 未知帳號）。
- `fetch` 用注入的假 client 測 happy path 一條。
- `main.py --dry-run`：只印不發、不寫檔，供本機（已 `gh auth`）試跑。
- ruff 全過、Python 3.13。

## 10. 動工前置 + git 流程
1. **驗證 username**：以 `gh api users/<login>` 逐一確認 §5.2 七個帳號真實存在，再定稿 `roles.py`。
2. **git**：本功能於 `feat/daily-status-sync` 分支開發，經 **PR + 1 approval** 併入 `main`（遵循現有保護規則），不直接推 main。
3. **首次對外動作**（push 分支、開 PR、Action 首跑發 Issue / 建 status 分支）皆**等 PM 確認後**才執行。

## 11. 未來升級路（不在本版）
- 方案 3：把 `publish` 的 CSV 段換成直接呼叫 Notion API upsert（加 Notion integration token + database_id 為 repo secret），達端到端零手動。因 `render` 已產出結構化 digest，升級只是新增一個輸出端，不需重寫。
