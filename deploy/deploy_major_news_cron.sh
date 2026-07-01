#!/usr/bin/env bash
# 部署「重大資訊每日 4 次直寫 core」排程（Cloud Run Job + Cloud Scheduler）
# 前置：gcloud CLI 已登入、具專案 Owner/Editor 權限可建立資源
set -euo pipefail

# ── 參數 ─────────────────────────────────────────────────────────────────────
PROJECT="polaris-desk-team"
REGION="asia-east1"                       # 與 BQ location 一致
JOB="major-news-cron"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/polaris/major-news-cron:latest"
REPO="polaris"                            # Artifact Registry repo
RUN_SA="major-news-cron@${PROJECT}.iam.gserviceaccount.com"
SCHED_SA="scheduler-invoker@${PROJECT}.iam.gserviceaccount.com"
SECRET="gemini-api-key"

gcloud config set project "$PROJECT"

# ── 0. 啟用 API ──────────────────────────────────────────────────────────────
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com bigquery.googleapis.com

# ── 1. Artifact Registry ─────────────────────────────────────────────────────
gcloud artifacts repositories create "$REPO" --repository-format=docker \
  --location="$REGION" --description="Polaris containers" 2>/dev/null || true

# ── 2. 服務帳號 ──────────────────────────────────────────────────────────────
gcloud iam service-accounts create major-news-cron \
  --display-name="Major News Cron (writes polaris_core)" 2>/dev/null || true
gcloud iam service-accounts create scheduler-invoker \
  --display-name="Cloud Scheduler → Run invoker" 2>/dev/null || true

# ── 3. IAM 權限（最小化）─────────────────────────────────────────────────────
# 3a. Run SA：BigQuery 讀寫 + job 執行 + 讀 secret
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${RUN_SA}" --role="roles/bigquery.dataEditor"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${RUN_SA}" --role="roles/bigquery.jobUser"
gcloud secrets add-iam-policy-binding "$SECRET" \
  --member="serviceAccount:${RUN_SA}" --role="roles/secretmanager.secretAccessor"
#   （進階：可把 dataEditor 收斂到只在 polaris_core dataset 上，見 README §權限收斂）

# 3b. Scheduler SA：可觸發此 Run Job
gcloud run jobs add-iam-policy-binding "$JOB" --region="$REGION" \
  --member="serviceAccount:${SCHED_SA}" --role="roles/run.invoker" 2>/dev/null || true

# ── 4. 建置映像 ──────────────────────────────────────────────────────────────
gcloud builds submit --tag "$IMAGE" \
  --config=/dev/stdin <<EOF
steps:
  - name: gcr.io/cloud-builders/docker
    args: ['build','-f','deploy/Dockerfile.major_news_cron','-t','${IMAGE}','.']
images: ['${IMAGE}']
EOF

# ── 5. Cloud Run Job ─────────────────────────────────────────────────────────
gcloud run jobs deploy "$JOB" \
  --region="$REGION" \
  --image="$IMAGE" \
  --service-account="$RUN_SA" \
  --set-env-vars="GCP_PROJECT=${PROJECT},BQ_DATASET=polaris_core,DEV_DATASET=,VECTOR_BACKEND=bigquery,MAJOR_NEWS_WINDOW_DAYS=3" \
  --set-secrets="GEMINI_API_KEY=${SECRET}:latest" \
  --max-retries=2 \
  --task-timeout=3600 \
  --memory=2Gi --cpu=2

# invoker 綁定（Job 建好後才能綁）
gcloud run jobs add-iam-policy-binding "$JOB" --region="$REGION" \
  --member="serviceAccount:${SCHED_SA}" --role="roles/run.invoker"

# ── 6. Cloud Scheduler × 4（08/12/16/20 Asia/Taipei）───────────────────────────
RUN_URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${JOB}:run"
for HH in 08 12 16 20; do
  gcloud scheduler jobs create http "major-news-${HH}00" \
    --location="$REGION" \
    --schedule="0 ${HH#0} * * *" \
    --time-zone="Asia/Taipei" \
    --uri="$RUN_URI" \
    --http-method=POST \
    --oauth-service-account-email="$SCHED_SA" \
    2>/dev/null || \
  gcloud scheduler jobs update http "major-news-${HH}00" \
    --location="$REGION" --schedule="0 ${HH#0} * * *" --time-zone="Asia/Taipei" \
    --uri="$RUN_URI" --http-method=POST --oauth-service-account-email="$SCHED_SA"
done

echo "✅ 部署完成。手動測試：gcloud run jobs execute ${JOB} --region ${REGION}"
