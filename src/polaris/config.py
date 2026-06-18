"""唯一設定來源 —— 全部從 .env 讀進來。

雲端與本地用同一份程式，差別只在 .env（或雲端環境變數）。
預設後端為 BigQuery（共用 canonical）；pgvector 為離線 fallback——換後端只改 VECTOR_BACKEND。
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- 向量庫後端開關（雲端 ↔ 本地就靠這個）---
    vector_backend: str = "bigquery"          # bigquery（預設）| pgvector（離線 fallback）

    # 雲端 BigQuery（預設後端）
    gcp_project: str = "polaris-desk-team"
    bq_dataset: str = "polaris_core"          # 共用唯讀 canonical
    dev_dataset: str = ""                     # 個人 scratch（polaris_dev_<name>）；寫入走這裡
    # 憲法 III / SOP §3.4：polaris_core 預設唯讀（client 端防呆，不取代 server ACL）。
    # 只有經 PM 同意的 ingestion 帳號（R1/R4，2026-06-08 起）設 BQ_ALLOW_CORE_WRITE=1。
    bq_allow_core_write: bool = False

    # 本地 pgvector（離線 fallback）
    database_url: str = "postgresql://polaris:polaris@localhost:5432/polaris"

    # LLM / 檢索金鑰（可留空，跑骨架測試不需要）
    gemini_api_key: str = ""
    cohere_api_key: str = ""
    tavily_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # 模型（名稱對齊 google-genai 當前版本）
    gemini_model_pro: str = "gemini-3-pro-preview"
    gemini_model_flash: str = "gemini-3-flash-preview"
    embedding_model: str = "gemini-embedding-2"   # 最新多模態嵌入；純文字可改 gemini-embedding-001
    embedding_dim: int = 768

    # Vertex AI（用 GCP 專案配額 / trial credit 跑「生成」，繞過 AI Studio 免費日配額）。
    # embeddings 一律仍走 api_key 同一模型，以保 polaris_core 既有 768 向量空間（別動）。
    gemini_use_vertex: bool = False           # GEMINI_USE_VERTEX=1 → 生成走 Vertex（ADC / SA 認證）
    vertex_location: str = "global"           # gemini-3-flash-preview 僅 global 端點可用（實測 2026-06-16）

    # LLM 成本 / 資源護欄（LLM10）
    llm_max_output_tokens: int = 4096         # 每次生成輸出上限（傳給 Gemini，擋失控長輸出）
    llm_token_budget: int = 0                 # process 累計 token 上限；0 = 無上限（預設）

    # 通知中心（specs/002）：內部 Slack incoming webhook。金鑰規則同憲法 III——
    # 只放 .env / Secret Manager，永不 commit；留空 = channel 自動停用（0 外呼）。
    slack_webhook_url: str = ""

    # 應用
    app_env: str = "local"                    # local | cloud
    log_level: str = "INFO"
    top_k: int = 8

    # R7 前端跨域（CORS）允許來源；逗號分隔。預設本地 dev（Next.js 3000 / Chainlit 8501）；
    # 雲端設成 R7 的 Vercel 網域（POLARIS_CORS_ORIGINS=https://<r7-domain>）。
    cors_origins: str = "http://localhost:3000,http://localhost:8501"

    # 使用者登入（R7-1：Google OAuth + Firestore 活動紀錄）。後端只需 client_id 驗
    # id_token 的 aud；client secret 留前端（NextAuth）。留空 = 任何 token 都驗不過 →
    # 全程匿名（token-free CI / 斷網降級照常）。Firestore 認證走 ADC（runtime SA），免金鑰。
    google_client_id: str = ""


# 全域單例 —— 其他模組 `from polaris.config import settings`
settings = Settings()
