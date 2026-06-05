# ===========================================================
# Polaris Desk — 容器化（W4 上 Cloud Run 用）
# 「我電腦能跑」= 「雲端能跑」，所以 W1 就先備好這個檔
# ===========================================================
# base image 對齊 pyproject requires-python>=3.13（用 3.12 會讓 pip install . 失敗）
FROM python:3.13-slim

# 系統相依（psycopg / 一些套件需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先複製相依定義，利用 layer cache
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

# 再複製程式
COPY src/ ./src/

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    APP_ENV=cloud

# Cloud Run 會以 $PORT 注入監聽埠；本地預設 8000（見 polaris/server.py:resolve_port）
EXPOSE 8000

# W4：thin FastAPI 後端（GET /healthz · POST /ask · POST /research，見 polaris/api.py）。
# uvicorn 監聽 $PORT（Cloud Run 注入）。無金鑰時引擎走 fallback，API 仍可回應。
# 離線 / 無 FastAPI 的純健康檢查另有 `python -m polaris.server`（stdlib 零依賴）。
CMD ["python", "-m", "polaris.api"]
