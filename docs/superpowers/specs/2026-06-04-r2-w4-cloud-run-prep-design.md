# R2 W4 上雲 prep（Cloud Run 部署機制）— 設計

**日期**：2026-06-04 **角色**：R2 架構師 **對應**：R2 spec D20–22（系統上雲）、SC-004/G4
**範圍決策**：使用者選「**只做部署機制（不動 API）**」——備好雲端管路與健康骨架，**不**提前拍板產品 `/ask` 表面。

## 1. 問題

R2 spec D20–22 要把後端上 Cloud Run，但這條路徑被兩件事擋著：①R4 ingestion（`polaris_core` 入庫，目前 PoC 中）②全員 GCP ADC 金鑰。等它們齊了再「第一次上雲」風險高（R2 風險對策明列「別把第一次上雲留到最後」）。

更直接的卡點：**Cloud Run 需要一個聽 `$PORT` 的 HTTP server，但目前後端只有 CLI**（`python -m polaris ask`）。現有 `Dockerfile` 的 `CMD` 是 placeholder（`python -c "import polaris..."`）、`docker-compose.yml` 的 `app` 服務被註解，兩者都 TODO 同一件事：`uvicorn polaris.api:app`。

## 2. 目標 / 非目標

**目標**：把「build → push → deploy → 祕密 → 健康探針」整條路徑備到**可重現**，且讓容器能在 Cloud Run **真正啟動並通過健康探針**。
**非目標**：不建產品 `/ask` 端點、不引入 FastAPI/uvicorn、不真的 deploy（無 R4 資料 + 不亂動雲端帳單）、不碰 5 節點 graph。

## 3. 設計

### 3.1 健康檢查骨架 `src/polaris/server.py`（零新依賴）
用標準函式庫 `http.server`（不引 FastAPI/uvicorn，貼合「不動 API」）：
- `resolve_port(env)`：讀 `$PORT`，缺省/壞值退 8000，**永不 raise**（容器不能因髒環境變數啟動失敗）。
- `health_payload()`：回 `{status, service, app_env, vector_backend}`——證明 import OK + `settings` 載入；**不含任何祕密**。
- `_HealthHandler`：`GET /healthz`（+ `/health`）→ 200；`/` → 200 提示；其餘 → 404。
- `build_server(port)`：`port=0` 取臨時埠（測試用）。`python -m polaris.server` 啟動。

### 3.2 容器與部署檔
- **Dockerfile**：`CMD` → `python -m polaris.server`（聽 `$PORT`）；base image `python:3.12-slim` → **`3.13-slim`**（修 latent bug：`requires-python>=3.13` 會讓 3.12 的 `pip install .` 失敗）。
- **`.dockerignore`（新）**：排除 `.env` / 金鑰 / `.git` / `.venv` / `tests` / `docs` 等——**金鑰絕不烘進映像**、縮小 build context。
- **docker-compose.yml**：解開 `app` 服務（`build: .`、`env_file: .env`、`ports 8000:8000`、`/healthz` healthcheck）；**不綁 db**（健康骨架不碰資料庫）。
- **Makefile**：`serve`（免 Docker 本地起）、`docker-build`、`docker-run`（本地 build+run+curl /healthz 煙測）。
- **`docs/上雲_Cloud_Run_runbook.md`（新）**：copy-paste 可重現步驟 + Secret Manager 映射表 + runtime SA 最小權限 + 健康探針驗證 + 待辦（依賴解除後補 `/ask` 與雲端 e2e）。placeholders only（無 billing ID、無金鑰）。

## 4. 不變量 / 安全
- **不碰** `graph/workflow.py`、`state.py`、`stubs.py`、compliance、R4 檔 → 5 節點 trace + `node_swap` hash 不變。
- server 是獨立新模組，只 `import settings` 讀設定，不接 graph。
- CI **維持 token-free**（健康骨架無 Gemini）；CI 不跑 `gcloud deploy`。
- `.env`/金鑰絕不進映像（`.dockerignore`）、絕不進 repo；runtime SA 最小權限（無 owner、無寫 core、無 billing）。

## 5. 測試（TDD）
`tests/test_server.py`（8 測，token-free）：`resolve_port` 預設/讀 `$PORT`/壞值退預設；`health_payload` status=ok + 不洩祕密；live server `/healthz`→200、`/`→200、未知路徑→404（臨時埠、daemon thread）。

## 6. 後續
接 `/ask`（API 任務）→ R4 ingestion 完成 → 真部署 → G4（D24）4 場景雲端可重現。本設計是上述的前置腳手架。
