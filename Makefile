# Polaris Desk — 常用指令（make <target>）
.PHONY: setup install dev db-up db-down test fmt lint check check-keys bq-smoke audit daily-status daily-status-dry serve serve-api docker-build docker-run

setup:          ## 一鍵建環境：Python 3.13 venv + 依賴 + .env 範本（人 / AI agent 都跑這個）
	test -d .venv || uv venv --python 3.13
	uv pip install -e ".[dev]"
	@test -f .env || cp .env.example .env
	@echo "✅ 環境就緒（Python 3.13）。下一步：① 打開 .env 填 GEMINI_API_KEY  ② gcloud auth application-default login（預設後端 BigQuery；離線 fallback 才需 make db-up）  ③ make test"

install:        ## 安裝相依（uv 優先，沒有用 pip）
	uv sync || pip install -e ".[dev]"

db-up:          ## 起本地 Postgres + pgvector（離線 / Demo fallback 才需要；預設後端是 BigQuery）
	docker compose up -d db

db-down:        ## 關閉本地資料庫
	docker compose down

test:           ## 跑測試
	.venv/bin/pytest -q

fmt:            ## 格式化
	.venv/bin/ruff format src tests

lint:           ## 檢查
	.venv/bin/ruff check src tests

check-keys:     ## 檢查 .env 內哪些 API 金鑰已設定（G1 閘門用）
	.venv/bin/python -m polaris doctor

bq-smoke:       ## BigQuery 雲端管路煙測（G2 用；不需 R4 入庫資料）
	.venv/bin/python -m polaris bq-smoke

daily-status:   ## 產生昨日各角色進度並更新滾動 Issue（需 GITHUB_TOKEN，本機可用 gh auth token）
	GITHUB_TOKEN=$${GITHUB_TOKEN:-$$(gh auth token)} PYTHONPATH=src .venv/bin/python -m polaris.daily_status --post-issue

daily-status-dry: ## 試跑：只印不發、不寫檔
	GITHUB_TOKEN=$${GITHUB_TOKEN:-$$(gh auth token)} PYTHONPATH=src .venv/bin/python -m polaris.daily_status --dry-run

serve-api:      ## 本地起 thin FastAPI 後端（/healthz · /ask · /research；R7 對接 / Cloud Run 入口）
	PORT=$${PORT:-8000} .venv/bin/python -m polaris.api

serve:          ## 本地起健康檢查骨架（stdlib 零依賴，只 /healthz；離線 / 無 FastAPI 時用）
	PORT=$${PORT:-8000} .venv/bin/python -m polaris.server

docker-build:   ## 建容器映像（W4 上雲 prep；映像內含健康骨架，/ask 待後續 API 任務）
	docker build -t polaris-desk:local .

docker-run:     ## 本地跑容器並煙測 /healthz（先 make docker-build）
	docker run --rm -d -p 8000:8000 --name polaris-app-smoke polaris-desk:local
	@sleep 2 && curl -fsS http://localhost:8000/healthz && echo "" && echo "✅ /healthz OK"
	@docker stop polaris-app-smoke >/dev/null

audit:          ## 依賴漏洞掃描（pip-audit；CI Security workflow 也會跑）
	uv pip install -q pip-audit
	.venv/bin/pip-audit --progress-spinner off

check: lint test  ## lint + test 一起跑
