# 上雲 Runbook — 後端 Cloud Run 部署（R2 · D20–22）

> **狀態（2026-06-04）：prep-staged，尚未真部署。**
> 本文把「build → push → deploy → 祕密 → 健康探針」整條路徑備好、可重現，讓 D20–22
> 真部署不必臨陣摸索（呼應 R2 風險對策「別把第一次上雲留到最後」）。
>
> 目前容器跑的是**健康檢查骨架**（`GET /healthz`，見 `src/polaris/server.py`）——
> 證明容器能在 Cloud Run 啟動並通過健康探針。**產品 `/ask` 端點＝之後的 API 任務**；
> 屆時把 `Dockerfile` 的 `CMD` 換成 `uvicorn polaris.api:app` 並補本節「雲端 e2e 煙測」。
>
> 真部署另一前提：**R4 ingestion 把 `polaris_core` 入庫完成**（目前 PoC 進行中）+ GCP ADC。

---

## 0. 一頁速覽

| 項目 | 值 |
|---|---|
| GCP 專案 | `polaris-desk-team` |
| 區域（region）| `asia-east1`（與 `polaris_core` / `gs://polaris-desk-raw` 同區，省跨區流量）|
| Cloud Run 服務名 | `polaris-api` |
| 容器埠 | 由 Cloud Run 以 `$PORT` 注入（`server.py` 會讀；本地預設 8000）|
| 健康探針路徑 | `GET /healthz` |
| 已開 API | `run`、`secretmanager`、`bigquery`、`storage`（R4 SOP §3.1 已開）|
| 祕密 | 5 把金鑰走 **Secret Manager**（絕不烘進映像、不寫進 repo）|

---

## 1. 前置（一次性）

```bash
# 認證 + 鎖定專案
gcloud auth login
gcloud config set project polaris-desk-team
gcloud auth application-default login          # 本地 ADC（BigQuery / 部署都會用到）

# 確認需要的 API 已開（R4 SOP §3.1 已開過，這裡只是驗證）
gcloud services list --enabled \
  --filter="config.name:(run.googleapis.com OR secretmanager.googleapis.com)" \
  --format="value(config.name)"
```

---

## 2. 祕密進 Secret Manager（金鑰絕不進映像 / repo）

只有「金鑰類」設定走 Secret Manager；非敏感設定走一般環境變數（見 §3）。

| `.env` 欄位 | Secret 名稱 | 必填？ |
|---|---|---|
| `GEMINI_API_KEY`   | `gemini-api-key`   | ✅（LLM 核心）|
| `COHERE_API_KEY`   | `cohere-api-key`   | ◐（Rerank）|
| `TAVILY_API_KEY`   | `tavily-api-key`   | ◐（Deep Research 網搜）|
| `ANTHROPIC_API_KEY`| `anthropic-api-key`| ◐（Eval 三方投票，平常不需）|
| `OPENAI_API_KEY`   | `openai-api-key`   | ◐（同上）|

```bash
# 建祕密 + 寫入版本（值從本地 .env 取，永不出現在指令歷史請改用 --data-file=-）
printf '%s' "$GEMINI_API_KEY" | gcloud secrets create gemini-api-key --data-file=- 2>/dev/null \
  || printf '%s' "$GEMINI_API_KEY" | gcloud secrets versions add gemini-api-key --data-file=-
# 其餘 4 把比照辦理（用得到才建）
```

---

## 3. 部署（build + deploy 一步到位）

`--source .` 會用本 repo 的 `Dockerfile` 在 Cloud Build 建映像後部署（最少手動步驟）。

```bash
gcloud run deploy polaris-api \
  --source . \
  --region asia-east1 \
  --allow-unauthenticated \
  --port 8000 \
  --service-account polaris-run@polaris-desk-team.iam.gserviceaccount.com \
  --set-env-vars "APP_ENV=cloud,VECTOR_BACKEND=bigquery,GCP_PROJECT=polaris-desk-team,BQ_DATASET=polaris_core" \
  --set-secrets "GEMINI_API_KEY=gemini-api-key:latest,COHERE_API_KEY=cohere-api-key:latest,TAVILY_API_KEY=tavily-api-key:latest"
```

- **非敏感設定**（`APP_ENV` / `VECTOR_BACKEND` / `GCP_PROJECT` / `BQ_DATASET`）→ `--set-env-vars`。
  對齊 `polaris/config.py` 的 `Settings` 欄位（同一份程式、雲端只換環境變數）。
- **金鑰** → `--set-secrets`（Cloud Run 執行期掛載成環境變數，映像裡沒有）。

---

## 4. 執行期服務帳號（最小權限）

建一個專用 runtime SA，**只給必要角色**：

```bash
gcloud iam service-accounts create polaris-run --display-name="Polaris Cloud Run runtime"

PROJ=polaris-desk-team
SA=polaris-run@$PROJ.iam.gserviceaccount.com

# 跑 BigQuery 查詢（讀 polaris_core 仍靠 dataset 層 READER，見 R4 SOP §3.4）
gcloud projects add-iam-policy-binding $PROJ --member="serviceAccount:$SA" --role="roles/bigquery.user"
# 讀取 Secret Manager 的金鑰
gcloud projects add-iam-policy-binding $PROJ --member="serviceAccount:$SA" --role="roles/secretmanager.secretAccessor"
# polaris_core 唯讀（dataset 層；R4=OWNER 寫入，本服務只讀）
bq update --dataset --source <(echo '{"access":[{"role":"READER","userByEmail":"'$SA'"}]}') $PROJ:polaris_core
```

> 最小權限原則：runtime SA **不**給 `roles/owner`、**不**給寫 `polaris_core`、**不**給 billing。

---

## 5. 驗證健康探針

```bash
URL=$(gcloud run services describe polaris-api --region asia-east1 --format='value(status.url)')
curl -fsS "$URL/healthz"     # → {"status":"ok","app_env":"cloud","vector_backend":"bigquery",...}
```

Cloud Run 預設對容器埠做啟動探針；本服務以 `/healthz` 回 200 即視為健康。

---

## 6. 本地煙測（免雲端，部署前先驗映像）

```bash
make docker-build       # 建映像
make docker-run         # 跑容器 + curl /healthz → ✅
# 或免 Docker：
make serve              # python -m polaris.server，另開終端 curl localhost:8000/healthz
```

---

## 7. 待辦（依賴解除後補）

- [ ] **接 `/ask` 產品端點**（API 任務）：`Dockerfile` `CMD` → `uvicorn polaris.api:app`，本文補「雲端 e2e 煙測」。
- [ ] **R4 ingestion 完成**：`polaris_core` 真有 chunks + 向量索引後，雲端才能跑出有引用的答案。
- [ ] **G4（D24）**：4 場景**在雲端**可重現（本 runbook 是其前置）。
- [ ] 成本護欄：Cloud Run min-instances=0（閒置不計費）、設並行與記憶體上限；對齊 R4 SOP §3.5 預算告警。

---

### 安全備註
- `.env` / 金鑰 **絕不進映像**（已由 `.dockerignore` 排除）、**絕不進 repo**。
- 真實 billing account ID 不寫進本（public）repo。
- 本 runbook 的指令皆為**手動執行**；CI 不跑任何 `gcloud deploy`（CI 維持 token-free）。
