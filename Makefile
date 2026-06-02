# Polaris Desk — 常用指令（make <target>）
.PHONY: setup install dev db-up db-down test fmt lint check check-keys daily-status daily-status-dry

setup:          ## 一鍵建環境：Python 3.13 venv + 依賴 + .env 範本（人 / AI agent 都跑這個）
	test -d .venv || uv venv --python 3.13
	uv pip install -e ".[dev]"
	@test -f .env || cp .env.example .env
	@echo "✅ 環境就緒（Python 3.13）。下一步：① 打開 .env 填 GEMINI_API_KEY  ② make db-up（起 pgvector）  ③ make test"

install:        ## 安裝相依（uv 優先，沒有用 pip）
	uv sync || pip install -e ".[dev]"

db-up:          ## 起本地 Postgres + pgvector
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

daily-status:   ## 產生昨日各角色進度並更新滾動 Issue（需 GITHUB_TOKEN，本機可用 gh auth token）
	GITHUB_TOKEN=$${GITHUB_TOKEN:-$$(gh auth token)} PYTHONPATH=src .venv/bin/python -m polaris.daily_status --post-issue

daily-status-dry: ## 試跑：只印不發、不寫檔
	GITHUB_TOKEN=$${GITHUB_TOKEN:-$$(gh auth token)} PYTHONPATH=src .venv/bin/python -m polaris.daily_status --dry-run

check: lint test  ## lint + test 一起跑
