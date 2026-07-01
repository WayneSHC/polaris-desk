# 重大資訊排程（方案 B：Cloud Run Job + Cloud Scheduler）

每日 **08:00 / 12:00 / 16:00 / 20:00（Asia/Taipei）** 自動抓 MOPS 重大訊息，
**冪等去重後直寫 `polaris_core`**（chunks + events）。

## 架構

```
Cloud Scheduler ×4 (cron, Asia/Taipei)
      │  POST run.googleapis.com/.../jobs/major-news-cron:run  (OAuth: scheduler-invoker SA)
      ▼
Cloud Run Job  (container: Playwright + scripts/cron_major_news_core.py)
      ├─ Secret Manager → GEMINI_API_KEY
      ├─ Service Account: major-news-cron（具 core 寫權限）
      ├─ 滾動視窗近 3 天 → 對 core 既有 ID 去重 → 只寫新資料
      └─ 直寫 polaris_core.chunks + polaris_core.events
Cloud Logging ← 每班摘要（抓 X／新增 Y／重複 Z）
```

## 為什麼冪等優先
- MOPS 揭露有補登延遲；每班掃「近 3 天」而非當天，晚到的也補得到。
- 寫前比對 core 既有 `chunk_id`/`event_id`，重疊部分零成本被擋 → 重跑、重疊班次皆安全。
- 任何一班失敗，下一班自動補齊（self-healing），無需人工重跑。

## 部署
```bash
cd polaris-desk
bash deploy/deploy_major_news_cron.sh
```
一次性完成：啟用 API、建 Artifact Registry、建 2 個 SA、綁 IAM、build 映像、
建 Cloud Run Job、建 4 個 Scheduler。

## 手動測試（不等排程）
```bash
gcloud run jobs execute major-news-cron --region asia-east1 --wait
gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=major-news-cron' \
  --limit 50 --freshness=1h
```

## 安全 / 權限
- **core 寫入無程式閘，純靠 IAM**：只有 `major-news-cron` SA 具 `bigquery.dataEditor`。
  一般 dev 帳號不應有此角色。
- **權限收斂（建議）**：把 `dataEditor` 從專案層收斂到只在 `polaris_core` dataset：
  ```bash
  bq update --dataset --source <(bq show --format=prettyjson polaris-desk-team:polaris_core \
    | jq '.access += [{"role":"WRITER","userByEmail":"major-news-cron@polaris-desk-team.iam.gserviceaccount.com"}]') \
    polaris-desk-team:polaris_core
  # 然後移除專案層的 dataEditor binding
  ```
- 金鑰永不落地：`--set-secrets` 由 Secret Manager 注入為環境變數，不寫進映像。

## 可靠性
- `--max-retries=2`：容器非零退出自動重試。
- `--task-timeout=3600`：單班上限 1 小時；MOPS 慢時仍足夠 20 家 × 3 天。
- 併發：4 個固定時間不重疊；即使某班超時與下班重疊，去重保證不重複。
- 監控：可對 Cloud Logging 建 log-based metric + 告警（連續 2 班錯誤 → 通知）。

## 調整
| 需求 | 改法 |
|------|------|
| 視窗天數 | env `MAJOR_NEWS_WINDOW_DAYS`（預設 3） |
| 執行時間 | 改 `deploy_*.sh` 的 `for HH in ...` 與 cron |
| 公司清單 | 自動讀 `company_dim`，新增公司免改程式 |
| 時區 | Scheduler `--time-zone`（現為 Asia/Taipei） |

## 沿用同一套做新聞 RSS
把 entrypoint 換成 `scripts/cron_news_core.py`（同款：滾動視窗 + 對 core 去重 +
直寫）即可，Dockerfile / SA / Scheduler 結構相同。
