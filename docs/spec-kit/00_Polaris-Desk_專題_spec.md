# 專題規格書（Spec Kit）：Polaris Desk（北辰）

**Project**: Polaris Desk — 台灣資本市場 Agent-Augmented Research Workflow（投研 + 法遵雙場景）
**Created**: 2026-05-31 **Status**: Draft **Sprint**: 4 週（Day 0 → Demo Day 28）
**Input**: PRD v1.1 / v1.1.1（`../Polaris Desk - PRD v1.1.md`）+ 4 週航程作戰計畫
**Team**: 7 人（R1–R7）· vibe coding · 無 AI / 金融 / BigQuery 既有經驗

---

## 一句話

> 一個會**自己查台股法說會與新聞、講得出處、還懂合規**的研究助手；4 週做出可在雲端重現的 5 分鐘 Demo。

---

## 🏛️ Constitution（專題憲法 — 不可違反，凌駕所有任務）

> 任何 user story / 任務 / PR 若違反以下原則即為 **No-Go**。對標 Spec Kit 的 constitution。

- **I. 合規紅線（NFR-031）**：新聞 / 投研功能**只描述、標證據、標矛盾，不得產出任何買賣建議**（投顧執照風險）。所有對外輸出皆受此約束；違反 = 直接砍該輸出。
- **II. 引用接地（Grounding）**：每一句結論 / 每個數字都必須可追溯到來源（法說稿頁碼 / 新聞出處 / 財報欄位）。無來源的宣稱不得輸出。
- **III. 雲端協作優先、金鑰永不外流**：開發預設用 BigQuery 共用 canonical `polaris_core`（算一次、大家讀），pgvector 留離線 fallback；金鑰只放 `.env` / GCP Secret Manager，**永不 commit、不貼群組、不進 Drive**（見決策 Q-03、Q-10）。
- **IV. Eval 即品質門檻**：功能「好不好」以 Ragas + 三方 Judge 的客觀分數為準，不以主觀感覺為準（≥ 80% 為硬門檻）。
- **V. Demo 可重現 + 離線備援**：Demo 跑**雲端**，但必須有「本地 pgvector + 預錄影片」的 Plan B；同一場景跑 10 次結果一致。
- **VI. 用當前最新技術棧**：Gemini 3（`gemini-3-pro-preview`/`-flash-preview`）+ 新版 `google-genai` SDK + `gemini-embedding-2`（多模態）；不得用已淘汰的 `google-generativeai`/`genai.configure`。

---

## 👤 User Scenarios & Testing（mandatory）

> 4 個 demo 場景 = 4 個 user story，依重要性排 P1/P2。每個都應可**獨立展示**並交付價值。
> 具體問句 / 期望輸出由 **R1 在 W2 Day 6–8 細寫**（見各 [NEEDS CLARIFICATION]）。

### User Story 1 — 單一公司投研摘要（Priority: P1）
分析師輸入「某公司某季表現如何」，系統檢索該公司法說稿 + 財報，產出**逐句附引用**的摘要。
- **Why P1**：最核心、最常用，撐起「會查、講得出處」的價值主張。
- **Independent Test**：只實作這一條即為可用 MVP。
- **Acceptance**：
  1. **Given** 已入庫的某公司某季法說稿，**When** 使用者問「該季營運重點」，**Then** 回傳 ≥ 3 點摘要、**每點都帶可點擊跳轉的來源**、且**無買賣建議**。
  2. **Given** 問及未入庫期間，**When** 查詢，**Then** 明確回「資料未涵蓋」而非編造。
- [NEEDS CLARIFICATION：示範公司 + 季別由 R1/R6 於 W2 定]

### User Story 2 — 同業比較（Priority: P1）
比較兩家公司同一財務指標（如毛利率），並標出差異與其來源。
- **Why P1**：PRD P1 功能（R1 W1 Day4 定義規格）；展示「跨文件對齊 + 計算接地」。
- **Acceptance**：
  1. **Given** A、B 兩公司皆已入庫，**When** 問「比較 A 與 B 的毛利率」，**Then** 回傳並列數字 + 各自來源 + 一句**中性**差異描述（不含買賣建議）。
  2. **Given** 計算結果，**Then** 每個數字皆可溯源到財報欄位（Calc grounding）。

### User Story 3 — 多模態圖表問答（Priority: P2 · 可砍）
針對法說 PDF 內的**圖表**提問，由 ColPali 多模態檢索回答。
- **Why P2**：差異化亮點，但依賴 ColPali POC；**G3 若 ColPali 失敗則連同本場景砍掉**。
- **Acceptance**：**Given** 含圖表的法說 PDF，**When** 問圖表內的數據，**Then** 正確回答並指出「出自第 N 頁圖表」。**門檻**：圖表題檢索命中率 ≥ 70%（否則砍，記 TD-01）。

### User Story 4 — 跨產業營收拆解（Priority: P1）
分析集團型公司（如鴻海）跨多產業的營收組成。
- **Why P1**：外部回饋納入的 P1 功能（FR-074~076）；有**獨立 10 題 eval**（AQ-06）。
- **Acceptance**：**Given** 多產業公司已標多產業 schema，**When** 問「各事業群 / 產業營收占比」，**Then** 回傳分產業拆解 + 來源，附加產業占比門檻依 AQ-08。
- [NEEDS CLARIFICATION：AQ-08 附加產業占比門檻 %（建議 10–15%），Day 4 由 R2/R6 定]

### 跨場景能力 — Watchdog 事件驅動合規（差異化亮點）
MOPS 一有新公告即觸發 Watchdog Agent 做合規初篩。於 demo 中作為「真 Agent」亮點呈現。
- **Acceptance**：**Given** 一則模擬 MOPS 公告，**When** 事件觸發，**Then** Watchdog 在 Alert Inbox 產出合規判斷摘要，**且不產出買賣建議**。

### Edge Cases
- 問及未入庫公司 / 期間 → 明確告知「資料未涵蓋」，不得編造。
- 來源彼此矛盾 → **標出矛盾**並列雙方出處，不替使用者下結論。
- 使用者要求「我該不該買」→ **拒答買賣建議**，改提供事實與證據（NFR-031）。
- 斷網 / 雲端故障（Demo Day）→ 切本地 pgvector + 預錄影片。

---

## ⚙️ Requirements（mandatory）

### Functional Requirements（對應 PRD）
- **FR-001**：系統 MUST 對台股法說稿 / 財報做 ingestion（解析→切塊→embedding→入庫），預設入 **BigQuery `polaris_core`**（pgvector 為離線 fallback）。
- **FR-002**：系統 MUST 提供 4-way 混合檢索（BM25 + 向量 + ColPali + Cohere Rerank）+ 新聞為第 5 路（FR-082）。
- **FR-003**：系統 MUST 以 Workflow（Planner→Retriever→Calculator→Writer→Compliance）端到端回答，**輸出逐句帶引用**。
- **FR-004**：系統 MUST 含 2 個真 Agent — Deep Research（ReAct loop）+ Watchdog（事件驅動合規）。
- **FR-005**：系統 MUST 支援同業比較與跨產業營收拆解（FR-074~076、含多產業 schema）。
- **FR-006**：系統 MUST 對所有對外輸出做合規檢查，**買賣建議數 = 0**（NFR-031）。
- **FR-007**：系統 MUST 支援時間範圍查詢（Temporal Anchoring，如「最近兩季」）。
- **FR-008**：系統 SHOULD 以 LLMLingua 壓縮 prompt 以省 token。

### Key Entities
- **Company / 公司**：含 GICS / 多產業分類（`gics_classifications`）。
- **Chunk / 法說稿段落**：含 `company`、`period`（供 Temporal Anchoring）、`embedding(768)`、來源頁碼。
- **News / 新聞**：第 5 路檢索來源，含可信度分級（AQ-09）。
- **Ontology / 台股分類字典**：公司 / 財務指標 / 事件 / 法遵名詞 四大類（R6 owns，G1 凍結）。
- **Eval Question / 題庫**：130 題 + 場景 4 獨立 10 題，含 golden answer。

---

## ✅ Success Criteria（mandatory · 可量測 · 技術無關）

- **SC-001**：Ragas — Context Precision ≥ **0.85**、Faithfulness ≥ **0.90**、Answer Relevance ≥ **0.85**。
- **SC-002**：130 題 Eval **≥ 80% 達標**（G3 硬門檻），場景 4 另有獨立 10 題。
- **SC-003**：130 題 + 4 場景 + 紅隊題中，**買賣建議 = 0**（NFR-031）。
- **SC-004**：4 個 demo 場景在**雲端環境**（Cloud Run + BigQuery）**可重現**（同場景跑 10 次結果一致）。
- **SC-005**：Demo Day 5 分鐘無斷點；斷網可於 < 30 秒切離線備援（本地 pgvector + 預錄影片）。
- **SC-006**：LLMLingua 對長 prompt 量到 token 節省 ≥ **50%**（目標 ~60%）。
- **SC-007**：每筆回答皆可追溯來源（引用覆蓋率 = 100% 的結論句）。

---

## 🚦 Milestones（Go / No-Go 閘 = 階段驗收）

| 閘 | Day | 過閘條件（= 該階段 acceptance）| 沒過 |
|---|---|---|---|
| **G1** | 5 | Ontology v1 凍結（含多產業 schema）+ 100 份法說稿入庫 **BigQuery `polaris_core`** | 延 1 天，砍 ESG 模組 |
| **G2** | 10 | e2e Workflow 跑通（問題進 / 帶引用答案出）+ Ragas 管線上線（Q-03 已定：BigQuery 為開發後端）| 砍「同業比較」 |
| **G3** | 17 | ColPali/LLMLingua 整合 + **Eval ≥ 80%** + Deep Research 可跑 + Watchdog 可跑 | ColPali 失敗→砍場景 3 + ColPali |
| **G4** | 24 | **4 場景在雲端可重現** + 離線備援可跑 + Watchdog 上線 + Eval ≥ 80% | 砍到 3 場景，保 1 場景 ≥ 90% |
| **Demo** | 28 | 5 分鐘無斷點，斷網切預錄 | — |

---

## 📌 Assumptions

- 100 份法說會 PDF 可合法取得且僅供研究、不對外散布（Q-09，Day 3 由 R4/R6 確認）。
- MOPS 無官方 API，先以手動 / 爬蟲取得（R4）。
- 團隊無金融 / 雲端經驗 → W1 前段排 ramp-up；上雲第一次部署排 Day 20–22、留 buffer，不留到 Demo 前夜。
- 預算 ~$400 USD：大頭是 LLM token（非 GCP infra）→ 三方 Judge 只在閘門跑、embedding 算一次重用、ColPali 用免費 GPU、設預算警報。
- 嵌入模型於 W1 ingest 前鎖定（換模型要全部重算）— 傾向 `gemini-embedding-2`（TD-01）。

## 🔎 Open Decisions（[NEEDS CLARIFICATION]，附到期 / owner）

| 編號 | 待決 | 到期 | owner |
|---|---|---|---|
| AQ-01 | 對外用詞「Agent-Augmented Research Workflow」 | Day 1 | R1 |
| Q-01 | 品牌名「Polaris Desk」定案 | Day 3 | R1 |
| Q-02 | Demo 對象（VC/老師/同學）影響故事調性 | Day 5 | R1 |
| Q-09 | 100 份 PDF 來源著作權 / 合規 | Day 3 | R4/R6 |
| AQ-08 | 多產業附加產業占比門檻 %（建議 10–15%）| Day 4 | R2/R6 |
| TD-01 | 嵌入模型 + ColPali 範疇 | Day 3 鎖模型 / Day 9 POC | R2/R4 |
| AQ-09 | 新聞可信度分級維護 | Day 12 | R6 |
| AQ-03 | Deep Research 框架選型 | Day 14 | R2 |
| Q-03 | 向量庫 pgvector→BigQuery 切換 | Day 10 | R2/R4 |（**已決，2026-06-02 更新**：直接以 BigQuery 共用 canonical 為開發後端，pgvector 留 fallback）
