# 上雲 Runbook — 後端 Cloud Run 部署（R2 · D20–22）

> **狀態（2026-06-16）：✅ 已真部署上線。** Service URL `https://polaris-api-14326813937.asia-east1.run.app`（revision `polaris-api-00006-gcz`）；`BQ_DATASET=polaris_core` 接真資料，`/ask` 回真 chunk 引用（`origin=embedding`）、Compliance passed；least-privilege runtime SA `polaris-run` + `gemini-api-key` Secret。雲端健康探針＝`GET /health`（見下）。
> _（原 prep-staged 紀錄保留供參。）_
> 本文把「build → push → deploy → 祕密 → 健康探針」整條路徑備好、可重現，讓 D20–22
> 真部署不必臨陣摸索（呼應 R2 風險對策「別把第一次上雲留到最後」）。
>
> 容器跑的是 **thin FastAPI 後端**（`src/polaris/api.py`）：`GET /healthz` · `POST /ask`
> （5 節點 workflow）· `POST /research`（Deep Research ReAct）——欄位對齊 R7 開工指南 §2 契約。
> 無金鑰時引擎走 fallback、API 仍可端到端回應（CI token-free）。
>
> **真部署仍待**：①R4 ingestion 把 `polaris_core` 入庫完成（目前 PoC 進行中）→ 雲端才有真資料可回；
> ②全員 GCP ADC。其餘部署機制與 API 皆已就緒。

---

## 0. 一頁速覽

| 項目 | 值 |
|---|---|
| GCP 專案 | `polaris-desk-team` |
| 區域（region）| `asia-east1`（與 `polaris_core` / `gs://polaris-desk-raw` 同區，省跨區流量）|
| Cloud Run 服務名 | `polaris-api` |
| 容器埠 | 由 Cloud Run 以 `$PORT` 注入（`server.py` 會讀；本地預設 8000）|
| 健康探針路徑 | `GET /health`（雲端）/ `GET /healthz`（本地）⚠️ Cloud Run 的 Google Front End 會攔截 `/healthz`，雲端一律用 `/health` |
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
  --set-env-vars "APP_ENV=cloud,VECTOR_BACKEND=bigquery,GCP_PROJECT=polaris-desk-team,BQ_DATASET=polaris_core,GEMINI_USE_VERTEX=1,POLARIS_CORS_ORIGINS=https://<r7-vercel-domain>" \
  --set-secrets "GEMINI_API_KEY=gemini-api-key:latest,NOTIFICATIONS_PRODUCER_TOKEN=notifications-producer-token:latest"
```

> ⚠️ `--set-secrets` / `--set-env-vars` 是**整組覆蓋**（不是合併）。線上 `polaris-api` 實際
> 還掛了 `GOOGLE_CLIENT_ID` / `google-client-secret` / `nextauth-secret` / `cohere-api-key` 等。
> **只想新增 / 換一把祕密時用 `--update-secrets`（合併，不動其它）**，例如本次加通知密鑰：
> `gcloud run deploy polaris-api --source . --region asia-east1 --update-secrets "NOTIFICATIONS_PRODUCER_TOKEN=notifications-producer-token:latest"`。
> 用上面整組 `--set-secrets` 重建前，請先 `gcloud run services describe polaris-api --region asia-east1`
> 把現有 env / secrets 補齊，否則會掉設定（如 OAuth 的 `GOOGLE_CLIENT_ID`）。

- **非敏感設定**（`APP_ENV` / `VECTOR_BACKEND` / `GCP_PROJECT` / `BQ_DATASET`）→ `--set-env-vars`。
  對齊 `polaris/config.py` 的 `Settings` 欄位（同一份程式、雲端只換環境變數）。
- **`GEMINI_USE_VERTEX=1`**：生成（`generate`）走 **Vertex AI**（用專案配額 / GenAI trial credit，
  繞過 AI Studio 免費日配額 429）。需 runtime SA 有 `roles/aiplatform.user`（見 §4）+ Vertex AI API 已開
  （`gcloud services enable aiplatform.googleapis.com`）。**嵌入（`embed`）仍走 `GEMINI_API_KEY` 同一模型**，
  保住 `polaris_core` 768 向量空間。模型 `gemini-3-flash-preview` 僅 `vertex_location=global` 可用（實測）。
- `gemini-api-key`（embeddings 用）+ `notifications-producer-token`（通知生產者端點守門，
  security review #2；runtime SA 需 `secretAccessor`，見 §4）。`APP_ENV=cloud` 未掛此密鑰 → `/notifications/events`
  與 `/reset` 一律 503（fail closed）。Tavily 為佔位，未建祕密（網搜 graceful skip）。
- **`POLARIS_CORS_ORIGINS`**：R7 前端（Vercel）跨域呼叫本 API 的允許來源。**部署時換成 R7 實際的
  Vercel 網域**（如 `https://polaris-desk.vercel.app`，多個逗號分隔）。本地 dev 預設已含
  `http://localhost:3000`（Next.js）/ `:8501`（Chainlit）。不設＝只允許本地，R7 線上會被 CORS 擋。
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
# 呼叫 Vertex AI（GEMINI_USE_VERTEX=1 的生成路徑；用專案配額 / trial credit）
gcloud projects add-iam-policy-binding $PROJ --member="serviceAccount:$SA" --role="roles/aiplatform.user"
# polaris_core 唯讀（dataset 層；R4=OWNER 寫入，本服務只讀）
bq update --dataset --source <(echo '{"access":[{"role":"READER","userByEmail":"'$SA'"}]}') $PROJ:polaris_core
```

> 最小權限原則：runtime SA **不**給 `roles/owner`、**不**給寫 `polaris_core`、**不**給 billing。

---

## 5. 驗證（健康探針 + API 端點）

```bash
URL=$(gcloud run services describe polaris-api --region asia-east1 --format='value(status.url)')
curl -fsS "$URL/health"      # → {"status":"ok","app_env":"cloud","vector_backend":"bigquery",...}
# ⚠️ 用 /health，不要用 /healthz：Cloud Run 的 Google Front End 攔截 /healthz（在抵達
#    容器前回自家 HTML 404）。app 兩條路徑都註冊，但雲端只有 /health 打得到容器。
curl -fsS -X POST "$URL/ask" -H 'content-type: application/json' \
  -d '{"query":"台積電 2025Q1 毛利率"}'        # → {answer, compliance_status, citations, trace}
curl -fsS -X POST "$URL/research" -H 'content-type: application/json' \
  -d '{"question":"比較台積電與聯發科最近兩季毛利率變化"}'  # → {final_answer, evidence, react_steps, status, ...}
```

Cloud Run 預設對容器埠做啟動探針；本服務以 `/healthz` 回 200 即視為健康。
`/docs`（FastAPI 自動 OpenAPI）可供 R7 對照契約。R4 入庫前，雲端回應走 fallback 語料。

---

## 6. 本地煙測（免雲端，部署前先驗映像）

```bash
make docker-build       # 建映像
make docker-run         # 跑容器 + curl /healthz → ✅
# 直接打 API（容器跑起來後）：
curl -s localhost:8000/ask -H 'content-type: application/json' -d '{"query":"台積電 2025Q1 毛利率"}'
# 或免 Docker：
make serve-api          # python -m polaris.api，另開終端 curl localhost:8000/healthz · /ask · /research
```

---

## 7. 待辦（依賴解除後補）

- [x] ~~接 `/ask` 產品端點~~ → **已完成**：`polaris/api.py`（`/ask` + `/research` + `/healthz`），`Dockerfile` `CMD` 已改 `python -m polaris.api`。
- [ ] **R4 ingestion 完成**：`polaris_core` 真有 chunks + 向量索引後，雲端才能跑出有引用的答案（目前 fallback 語料）。
- [ ] **G4（D24）**：4 場景**在雲端**可重現（本 runbook 是其前置）。
- [ ] 成本護欄：Cloud Run min-instances=0（閒置不計費）、設並行與記憶體上限；對齊 R4 SOP §3.5 預算告警。見 §8。

---

## 8. 成本護欄（匿名濫用 / 成本型 DoS）

威脅：匿名請求打 `/ask` `/research` 觸發 LLM + 檢索，燒 Gemini / Vertex 配額。三層防護：

### 8.1 後端收口 internal（Phase 0；擋「直連 api」）

把 `polaris-api` 收成內部 ingress，配前端用 VPC connector server-to-server 連入——公網
打不到後端的 `*.run.app`。前端（`polaris-web`）仍是唯一公開前門，經 `next.config.ts` 的
`rewrites()` proxy `/api/*`（`/api/auth` 留前端給 NextAuth）。

```bash
PROJ=polaris-desk-team; REGION=asia-east1
gcloud services enable vpcaccess.googleapis.com
# /28 網段別撞到現有 subnet（這是唯一要你決策的數字）
gcloud compute networks vpc-access connectors create polaris-connector \
  --region $REGION --network default --range 10.8.0.0/28
# 後端收口（用 update，不碰 env/secret；設 internal-and-cloud-load-balancing 讓日後接 ALB 免再改）
gcloud run services update polaris-api --region $REGION \
  --ingress internal-and-cloud-load-balancing
# 前端掛 connector + 全 egress（讓 web→api 的 run.app 呼叫被視為 VPC 內部）
gcloud run services update polaris-web --region $REGION \
  --vpc-connector polaris-connector --vpc-egress all-traffic
# 驗收：公網應打不到後端，瀏覽器走 web /api proxy 仍正常
API=$(gcloud run services describe polaris-api --region $REGION --format='value(status.url)')
curl -sS -o /dev/null -w "%{http_code}\n" "$API/health"   # 期望 404（Google 前端擋下，任何路徑皆同；2026-07-08 實測）
```

註：`/healthz` 是 run.app 網域的 GFE 保留路徑——即使經 VPC 內部流量也到不了 app
（2026-07-08 經 web proxy 實測：`/api/healthz` 回 Google 404、`/api/<其他路徑>` 回
FastAPI JSON 404）。健康檢查打 run.app URL 時請用 `/health` 等非保留路徑。

### 8.2 app 層限流（擋「匿名經 web /api/* 代轉」這條缺口）

§8.1 只擋直連；匿名仍可經公開的 `polaris-web` `/api/ask` 代轉燒配額（後端 `current_user`
可選、匿名放行）。`polaris/ratelimit.py` 的固定視窗限流器補上：`/ask` `/research` 每來源
（XFF / 對端 IP）每 60s ≤ `RATE_LIMIT_PER_MIN`。**只在 `APP_ENV=cloud` 生效**（local/CI/demo
不限流，保 token-free）；設 `0` 關閉。超限 → 429 + `Retry-After: 60`。

```bash
gcloud run services update polaris-api --region $REGION \
  --max-instances 5 \
  --update-env-vars RATE_LIMIT_PER_MIN=20
```

> ⚠️ 限流是**單一進程內存**：多 instance 時各自計數，全域上限 ≈ `RATE_LIMIT_PER_MIN × instances`，
> **所以一定要搭 `--max-instances`** 才得到有界的成本天花板。要嚴格全域限流需改 Redis/Firestore。
> XFF 可偽造，此處作「成本分桶」非身分驗證；要更硬可由 web proxy 注入受信 header 當 key。

### 8.3 預算天花板（鈍器，兜底）

`--max-instances` 封住並行 instance 數 → 封住花費上界；另設 GCP 預算告警（R4 SOP §3.5）。

### 8.4 輸入端守門分階段上線（防止使用者亂問）

輸入端 defense-in-depth，四層各自獨立 flag、**全預設 off**（行為零變動，同 `VISION_EXTRACTION` 慣例）。
與輸出端 compliance 對稱：確定性 floor 先跑、LLM smart 後跑、攔截零改寫（固定訊息）。

| 層 | flag | 風險 | 說明 |
|---|---|---|---|
| L1 注入 | `INPUT_GATE_INJECTION` | 零誤判 | 確定性 prompt-injection / jailbreak 攔截，命中即擋不諮詢 LLM |
| L3 查無資料 | `INPUT_GATE_NO_EVIDENCE` | 零誤判 | 檢索+計算後 contexts 仍空 → 回固定訊息、不讓 writer 生成（防幻覺） |
| L2 範圍 | `INPUT_GATE_SCOPE` | 需先驗 | floor 正向放行（ticker/關鍵字）+ Gemini Flash 分類離題；LLM 掛時 fail-open |
| L0 配額 | `DAILY_QUESTION_QUOTA` | 需流量 | 每人每日題數；登入 keyed on sub、匿名 keyed on IP；只在 `APP_ENV=cloud` 生效 |

**⚠️ 一律用 `--update-env-vars`（增量合併），別用 `--set-env-vars`**（整組覆蓋會清掉線上既有
`APP_ENV`/`VECTOR_BACKEND`/`GEMINI_USE_VERTEX`/`CORS` 等變數，見 §5 的整組覆蓋警告）。

**Step 1 — 先開零誤判的 L1 + L3（可立即上線）：**
```bash
gcloud run services update polaris-api --region $REGION \
  --update-env-vars "INPUT_GATE_INJECTION=1,INPUT_GATE_NO_EVIDENCE=1"
```

**Step 2 — 開 L2 範圍層前，先驗 false-block（避免 LLM 誤擋真問題）：**
```bash
# 在有 GEMINI_API_KEY 的環境跑；對 eval questions_v1（142 題正當投研題）量誤擋率
GEMINI_API_KEY=<key> python scripts/scope_gate_check.py
# 誤擋率接近 0 才開；偏高 → 擴 input_gate._SCOPE_KEYWORDS 或調 SCOPE_SYSTEM_PROMPT
gcloud run services update polaris-api --region $REGION \
  --update-env-vars "INPUT_GATE_SCOPE=1"
```

**Step 3 — 觀察真實流量後再設每日配額（數字別用猜的）：**
```bash
# 看 p95 questions/user/day，設 ~3–5×；0=關
gcloud run services update polaris-api --region $REGION \
  --update-env-vars "DAILY_QUESTION_QUOTA=50"
```

> 回滾：把對應 flag `--update-env-vars "INPUT_GATE_SCOPE=0"` 即可，逐層獨立、互不影響。

---

### 安全備註
- `.env` / 金鑰 **絕不進映像**（已由 `.dockerignore` 排除）、**絕不進 repo**。
- 真實 billing account ID 不寫進本（public）repo。
- 本 runbook 的指令皆為**手動執行**；CI 不跑任何 `gcloud deploy`（CI 維持 token-free）。
