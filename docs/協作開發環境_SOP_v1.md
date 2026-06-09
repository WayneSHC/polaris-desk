# Polaris Desk 協作開發環境 SOP v1.2

**目的**：讓 7 位成員在「同一份可信資料」上協同開發，且把成本壓在 GCP 免費額度內。
**適用範圍**：4 週 MVP 開發期（W1 ~ W4）。
**文件擁有者**：角色 1（PM）。**基礎設施擁有者**：角色 4（資料工程師）。

> **基礎設施現況（2026-06-02）**：GCP 專案 **`polaris-desk-team`** 已建立並連結計費。**§3.1–§3.4 已完成**：4 個 API 已開、`gs://polaris-desk-raw` 已建、`polaris_core`（空）已建、6 位成員權限已綁定（5 READER + R4 OWNER）。**剩下：§3.5 預算護欄、§4 ingestion（角色 4）、每人 §5 建自己的 scratch。**
> **本團隊用個人 `@gmail.com` 帳號、無 Google Workspace 網域**，故權限以個別 `user:` 綁定（見 §3.4），不使用 Google Group。

---

## 0. 核心原則（先讀這段）

1. **算一次、大家讀**：所有人共用一份唯讀的 canonical 資料，個人實驗寫進自己的 scratch，不互相覆蓋。
2. **共用不等於同寫**：禁止 7 個人各自全量重建 index 或重跑 ingestion，那會放大成本並造成資料不一致。
3. **預設讀 `polaris_core`、寫 `polaris_dev_<name>`**：程式碼層級就要鎖死這個預設。
4. **成本守則**：dev 期所有用量壓在 BigQuery 與 Cloud Run 免費額度內，$300 credit 留到 W4 demo。

---

## 1. 角色與權責

| 角色 | 權責 | 對 `polaris_core` 權限 |
| --- | --- | --- |
| 角色 1（PM／R1） | 維護本 SOP、建立專案、設定預算告警、核准 schema 變更 PR | WRITER（2026-06-08 起，破例升級） |
| 角色 4（資料工程師） | 建置基礎設施、跑 ingestion、寫入 canonical | OWNER／WRITER（人帳號 + GCE 預設 SA） |
| 角色 2（AI 架構師） | 審查 schema migration、retrieval 設定 | READER |
| 其餘開發者 | 讀 core、在自己的 scratch 做實驗 | READER |

> ~~只有角色 4 能寫入 `polaris_core`。其他人一律唯讀。~~
> **2026-06-08 更新**：經 PM 同意破例，`polaris_core` 的 WRITER 已擴大到 R4（人帳號 OWNER + GCE 預設 SA WRITER）與 R1（WRITER）；其餘成員仍唯讀。詳見 §3.4 變更註記與風險說明。schema／index 變更仍一律走 §7 PR。

---

## 2. 環境總覽（三層）

單一團隊 GCP Project：`polaris-desk-team`

```
polaris-desk-team
├─ Cloud Storage：gs://polaris-desk-raw       ← PDF 原始檔（檔案層單一真實來源）
├─ BigQuery dataset：polaris_core             ← canonical，全員唯讀
│    chunks / embeddings（VECTOR INDEX）/ colpali_index / financial_metrics / ontology
└─ BigQuery dataset：polaris_dev_<name>       ← 每人一個，可寫，做實驗用
```

設定一致的占位符（請全團統一）：

| 變數 | 值 |
| --- | --- |
| `PROJECT_ID` | `polaris-desk-team` |
| `REGION` | `asia-east1`（台灣，低延遲與資料落地） |
| `RAW_BUCKET` | `gs://polaris-desk-raw` |
| `CORE_DATASET` | `polaris_core` |
| 團隊成員 | 7 位成員的個人 `@gmail.com`（IAM 以 `user:` 個別綁定，見 §3.4） |

> **注意**：建立 VECTOR INDEX 前，請角色 4 先確認所選 REGION 支援 BigQuery `CREATE VECTOR INDEX`。若不支援，改用支援的鄰近區域並同步更新本表。

---

## 3. Phase 1：一次性基礎設施建置（角色 4 執行，約 30 分鐘）

> **✅ §3.1–§3.4 已由 PM 於 2026-06-02 執行完成**（API 已開、bucket 與空 `polaris_core` 已建、6 位成員權限已綁定）。以下指令保留供查核與日後 Terraform 重建。**角色 4 從 §4 開始**（建表 + 向量索引 + ingestion）；§3.5 成本護欄仍待設定。

以下用 `gcloud`／`bq` 指令快速建置。建議事後由角色 4 把同一份設定補成 Terraform（PRD §23.3）以便重建。

### 3.1 設定 project 與 API

```bash
gcloud config set project polaris-desk-team

gcloud services enable bigquery.googleapis.com run.googleapis.com \
  storage.googleapis.com secretmanager.googleapis.com
```

### 3.2 建立原始檔 bucket

```bash
gcloud storage buckets create gs://polaris-desk-raw \
  --location=asia-east1 \
  --uniform-bucket-level-access
```

### 3.3 建立 canonical dataset

```bash
bq --location=asia-east1 mk --dataset \
  --description "canonical read-only corpus" \
  polaris-desk-team:polaris_core
```

### 3.4 設定權限（IAM）— 個別 user 綁定（✅ 已完成）

本團隊無 Workspace 網域，**逐一綁定成員的 gmail**（不使用 Google Group）。專案 owner（PM）不需綁，owner 角色已涵蓋。

**專案層角色用 `roles/bigquery.user`，不是 `jobUser`**：`jobUser` 只能跑查詢、**不能建 dataset**，會卡住 §5 步驟 2（每人要建自己的 scratch）。`bigquery.user` = 跑 job ＋ 建自己的 dataset，但**不會**自動取得任何 dataset 的資料讀取權（讀 `polaris_core` 仍要下方 dataset 層 READER）。

**本機跑 BigQuery（ADC）還要 `roles/serviceusage.serviceUsageConsumer`**：在本機用 `gcloud auth application-default login` + `set-quota-project polaris-desk-team` 時，設定 quota project 需要 `serviceusage.services.use` 權限，只在這個角色裡。少了它會卡在 `set-quota-project`，報 `does not have the "serviceusage.services.use" permission`。所以本機開發者要同時綁 `bigquery.user` ＋ `serviceUsageConsumer`。指令：

```bash
for m in "${MEMBERS[@]}"; do
  gcloud projects add-iam-policy-binding polaris-desk-team \
    --member="user:$m" --role="roles/serviceusage.serviceUsageConsumer" --condition=None
done
```

```bash
# 把成員的 gmail 填進來（owner/PM 不用列）
MEMBERS=(
  "member1@gmail.com"
  # ...其餘成員
)

# 每人都能跑查詢 ＋ 建自己的 scratch dataset
for m in "${MEMBERS[@]}"; do
  gcloud projects add-iam-policy-binding polaris-desk-team \
    --member="user:$m" \
    --role="roles/bigquery.user"
done
```

把成員設為 `polaris_core` 的 dataset 層權限（一般成員 `READER`、角色 4 `OWNER`）：

```bash
# 1. 匯出現有 access 設定（此檔含真實 email/ACL，已在 .gitignore，不要 commit）
bq show --format=prettyjson polaris-desk-team:polaris_core > core_access.json

# 2. 在 core_access.json 的 "access" 陣列加入：
#    一般成員 → { "role": "READER", "userByEmail": "memberX@gmail.com" }
#    角色 4   → { "role": "OWNER",  "userByEmail": "<R4 的 gmail>" }

# 3. 套用
bq update --source=core_access.json polaris-desk-team:polaris_core
```

> **實際已綁定（2026-06-02 初設）**：6 位成員專案層 `roles/bigquery.user`；`polaris_core` dataset → R4（吳瑾瑜）`OWNER`、其餘 5 位 `READER`、PM 為 creator/`OWNER`。
>
> **2026-06-08 變更（破例，已獲 PM 同意）**：為了讓 R1／R4 能直接寫入 canonical，`polaris_core` 的 WRITER 名單已擴大，**不再是「只有 R4 能寫」**：
> - `holajennytw@gmail.com`（R4 ingester 人帳號）→ `OWNER`
> - `736393260540-compute@developer.gserviceaccount.com`（R4 runtime 用的 GCE 預設 SA）→ `WRITER`
> - `hbb97.tw@gmail.com`（R1）→ `WRITER`（由原 READER 升級）
> - R1／R4 人帳號另綁專案層 `roles/serviceusage.serviceUsageConsumer`（本機 ADC 用）
>
> ⚠️ 兩點風險：(1) 用的是 GCE **預設** SA，專案內任何跑在預設 SA 上的服務都能寫 `polaris_core`，較鬆；要收緊可改建專用 SA（例如 `r4-ingester@`）只授這個 dataset。(2) 多人可寫 canonical → schema／index 變更要走 §7 PR 流程，別各自直接改。這牴觸憲法「🔴 不可寫 `polaris_core`／只有 R4 寫 core」，屬團隊有意識的破例，若日後收回請同步改回本段與下方 §1／§9 表格。
>
> **2026-06-09 補綁**：R5（楊宗勲，`arronyang0416@gmail.com`，Eval Lead）一次開齊本機開發三件套——專案層 `roles/bigquery.user` ＋ `roles/serviceusage.serviceUsageConsumer`、`polaris_core` dataset 層 `READER`。W2 e2e 切真資料前先把權限備齊，避免卡在申請等待。
>
> 應用程式用的 service account 採最小權限，金鑰存進 Secret Manager，**不進版控**。
> 新增／移除成員時，記得同步更新專案層 `bigquery.user`／`serviceUsageConsumer` 綁定與 `polaris_core` 的 READER／WRITER 名單。

### 3.5 設定成本護欄（重要）

1. **預算告警**：

   ```bash
   gcloud billing budgets create \
     --billing-account=YOUR_BILLING_ACCOUNT_ID \
     --display-name="polaris-dev-budget" \
     --budget-amount=400USD \
     --threshold-rule=percent=0.5 \
     --threshold-rule=percent=0.9
   ```

2. **per-user 查詢配額**：到 Console 的「IAM 與管理 → 配額與系統限制」，搜尋 `Query usage per day per user`，設一個每人每日掃描上限（例如 200 GB／人／日），防止單人亂掃表把免費 1 TB／月吃光。

---

## 4. Phase 2：canonical 資料建置（角色 4 執行，一次性）

### 4.1 建立分區與分群表（控制掃描量的關鍵）

```sql
CREATE TABLE polaris_core.chunks (
  chunk_id      STRING,
  ticker      STRING,
  doc_type      STRING,
  fiscal_period STRING,
  published_at  DATE,
  chunk_text    STRING,
  embedding     ARRAY<FLOAT64>
)
PARTITION BY published_at
CLUSTER BY ticker, doc_type;
```

> 所有查詢都應帶 `published_at` 範圍與 `ticker` 條件，才能命中 partition／cluster，把掃描量壓到最小。

### 4.2 建立向量索引（對齊 PRD §15）

```sql
CREATE VECTOR INDEX chunks_emb_idx
ON polaris_core.chunks(embedding)
OPTIONS(index_type = 'IVF', distance_type = 'COSINE');
```

> ⚠️ **兩個前提**：①`asia-east1` 須支援 `CREATE VECTOR INDEX`（建前先確認，否則改鄰近區域並更新 §2）。
> ②**BigQuery 不會在少於 5,000 列的表上建立向量索引**。100 份法說稿切 chunk 後若不足 5,000 列，索引不會生成，`VECTOR_SEARCH` 會自動退回暴力搜尋（demo 仍可用，但要知道）。

### 4.3 跑一次 ingestion

由角色 4 用 ingestion pipeline 把 100 份法說稿、財務指標、ColPali index、ontology 一次寫入 `polaris_core`。embedding 與 ColPali **只在此處計算一次**，其他人不得重算。對齊 PRD §1.5 的 W1 Day 5「Ontology 凍結 + 100 份法說稿入庫」。

完成後通知全團：**canonical 已就緒，可開始開發**。

---

## 5. Phase 3：每位開發者上線步驟（給大家的 onboarding）

每個人只需做一次。預計 10 分鐘完成。

### 步驟 1：登入並指定 project

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project polaris-desk-team
```

### 步驟 2：建立自己的 scratch dataset

把 `<name>` 換成你的英文名（例如 `wayne`）：

```bash
bq --location=asia-east1 mk --dataset \
  polaris-desk-team:polaris_dev_<name>
```

### 步驟 3：取得共用設定

`PROJECT_ID` 與 `CORE_DATASET` 已在版控的 config 模組中，全團一致，不要自行改動。只需在本機設定自己的 scratch：

```bash
# 寫進本機 .env（不要進版控）
echo "DEV_DATASET=polaris_dev_<name>" >> .env
```

範例 config 讀取邏輯：

```python
import os

PROJECT_ID   = "polaris-desk-team"        # 進版控，全團一致
CORE_DATASET = "polaris_core"             # 進版控，唯讀
DEV_DATASET  = os.environ["DEV_DATASET"]  # 個人覆寫，可寫
```

### 步驟 4：驗證讀取權限

```bash
bq query --use_legacy_sql=false \
  'SELECT COUNT(*) AS n FROM `polaris-desk-team.polaris_core.chunks`'
```

> 能回傳數字即代表 onboarding 成功。

---

## 6. 日常開發守則

1. **讀 `polaris_core`，寫 `polaris_dev_<name>`**。任何寫入操作的目標 dataset 一律是自己的 scratch。
2. 禁止對 `polaris_core` 做 ingestion、重建 index、改 schema。需要新資料或新欄位，走第 7 章流程。
3. 每次查詢必帶 partition filter（`published_at` 範圍）與 `ticker` 條件。
4. 大查詢前先 dry-run 估成本：

   ```bash
   bq query --dry_run --use_legacy_sql=false 'YOUR_SQL'
   ```

5. 重複查詢盡量用相同 SQL 以命中 cached results（快取結果免費）。

---

## 7. Schema 變更流程

1. 在自己的 scratch 驗證新 schema 或新欄位可行。
2. 開 PR，附上 migration SQL 檔（放 `migrations/` 目錄）與變更理由。
3. 角色 2（AI 架構師）審查，角色 1（PM）核准。
4. 由角色 4 對 `polaris_core` 套用 migration，並重建受影響的 index。
5. 通知全團 canonical schema 已更新版本。

> 禁止繞過此流程直接動 canonical，避免 schema drift。

---

## 8. 成本護欄速查

| 機制 | 設定者 | 效果 |
| --- | --- | --- |
| canonical 算一次 | 角色 4 | 避免 embedding／ColPali 被乘以人數 |
| partition + cluster | 角色 4 | 把每次查詢掃描量壓進免費 1 TB／月 |
| 預算告警 50%／90% | 角色 1 | 超支前先收到通知 |
| per-user 查詢配額 | 角色 4 | 防單人亂掃表 |
| Cloud Run scale to zero | 全員 | 沒人用就不計費 |
| $300 credit 留到 W4 | 角色 1 | dev 期走免費額度，demo 期才動用 |

> 不要為了協作引入外部託管向量庫（如 Qdrant Cloud）。它的免費 tier 容量不足以承載 ColPali leg，會被迫升級為月費叢集，與省錢目標衝突。

---

## 9. 失敗排查（Fail Fast：Status / Root Cause / Suggested Fix）

| 現象 | 最可能原因 | 第一步排查 |
| --- | --- | --- |
| 查 core 報 permission denied | 你的 gmail 沒被綁定，或缺 `bigquery.user` | 確認帳號已加入 §3.4 的 `user:` 名單（專案層 `bigquery.user` + `polaris_core` READER） |
| 建不了自己的 scratch dataset | 只有 `jobUser`、缺 `datasets.create` | 確認專案層角色是 `roles/bigquery.user`（非 `jobUser`） |
| `set-quota-project` 報 `serviceusage.services.use` 缺權限 | 本機 ADC 設 quota project 需要 `serviceUsageConsumer` | 綁專案層 `roles/serviceusage.serviceUsageConsumer`（見 §3.4） |
| `Method doesn't allow unregistered callers`／`unregistered callers` | 請求完全沒帶身分＝ADC 沒登入或被 `GOOGLE_APPLICATION_CREDENTIALS` 指到壞檔 | 本機：`gcloud auth application-default login` 再 `set-quota-project`；檢查並 `unset GOOGLE_APPLICATION_CREDENTIALS`。GCE/Cloud Run：確認跑在有 BQ 權限的 SA 上 |
| 查詢費用異常高 | 沒帶 partition filter，全表掃描 | 加 `published_at` 範圍與 `ticker` 條件，先 dry-run |
| 寫入失敗 | 誤把目標設成 `polaris_core` | 確認寫入目標是 `polaris_dev_<name>` |
| 大家資料對不上 | 有人在 scratch 改了卻當成 canonical | 一律以 `polaris_core` 為準，scratch 只是個人實驗 |
| VECTOR INDEX 建立失敗 | REGION 不支援，或表 < 5,000 列 | 改用支援的鄰近區域（更新 §2）；列數不足則等資料補足或接受暴力搜尋 |
| `project not found` / 設不了 project | 用到了顯示名稱而非 Project ID | 一律用 Project ID `polaris-desk-team` |

---

## 10. 啟動檢查清單（Definition of Ready）

- [x] 單一團隊 project `polaris-desk-team` 已建立並開啟計費
- [ ] 預算告警與 per-user 配額已設定
- [x] `gs://polaris-desk-raw` 已建立
- [x] `polaris_core` 已建立，6 位成員專案層 `bigquery.user`；dataset 層：R4 OWNER + R1 WRITER + R4 GCE 預設 SA WRITER，其餘 READER（2026-06-08 破例擴大，見 §3.4）
- [ ] canonical（chunks / embeddings / VECTOR INDEX / 財務指標 / ontology）已 ingest 一次
- [ ] 7 位成員各自建立 scratch dataset 並通過讀取驗證
- [ ] config 模組（`PROJECT_ID` / `CORE_DATASET`）已進版控

> 已完成：project/billing、bucket、`polaris_core` + 權限。**剩下三項**＝§3.5 成本護欄、§4 ingestion（角色 4）、每人 §5 建 scratch。全部勾選後即就緒。

---

_版本：v1.3　|　對應 PRD：§13.4（向量檢索）、§23（部署）、§24（成本）_
_v1.3 變更（2026-06-08）：經 PM 同意破例擴大 `polaris_core` WRITER（R1 升 WRITER、R4 GCE 預設 SA 加 WRITER），不再是「只有 R4 寫 core」；§3.4 補上本機 ADC 需 `serviceUsageConsumer`；§1 角色表、§3.4 變更註記＋風險、§9 排查（`serviceusage.services.use`／unregistered callers）、§10 清單同步更新。憲法層「不可寫 `polaris_core`」仍為原則，本次為有意識破例。_
_v1.2 變更（2026-06-02）：§3.1–§3.4 已實際執行完成（API／bucket／空 `polaris_core`／6 人權限）；專案層角色由 `bigquery.jobUser` 修正為 `roles/bigquery.user`（jobUser 無法建 scratch dataset，會卡 §5）；§3.4 改為一般成員 READER、角色 4 OWNER；§9、§10 同步更新。_
_v1.1 變更：專案改用乾淨 Project ID `polaris-desk-team`；IAM 從 Google Group 改為個別 `user:` 綁定（團隊用個人 gmail、無 Workspace 網域）；補上 Phase 0 現況、向量索引 region／5,000 列前提，與 Project ID vs 顯示名稱排查。_
