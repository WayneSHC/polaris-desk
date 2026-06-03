# Polaris Desk Constitution

> 北辰（Polaris Desk）— 台灣資本市場 Agent-Augmented Research Workflow。
> 這份憲法是專題開發的**最高守則**。任務、計畫、PR 跟它衝突，一律以它為準。
> 違反 = **No-Go**：停下、改方案、不硬幹。
> 完整團隊規格在 Google Drive `Polaris Desk/03_規格書_PRD/spec-kit/`
>（含專題 spec + 7 角色 spec）。

## Core Principles

### I. 合規紅線 — NFR-031（NON-NEGOTIABLE）

我們**沒有投顧執照**。任何對外輸出（新聞卡、投研摘要、Watchdog 警報、Deep Research 報告）
**只准做三件事**：描述事實、標出來源、標出矛盾。

**不准出現**這 6 個字眼（W1 D1 攔截清單）：
建議買進、建議賣出、加碼、減碼、看多、看空。
R6 W3 會補完整關鍵字 / regex / 紅隊測試。

防線分三層：
- **Compliance 節點**：每個答案出去前的最後關卡，命中關鍵字 → 改回固定訊息「本系統不提供買賣建議，僅描述事實與引用來源。」
- **Watchdog Agent**：事件驅動掃描所有對外輸出（W3 上線）
- **新聞卡 UI**：前端再過一次（W4）

**達標數字**：130 題 + 4 場景 + 紅隊測試中，買賣建議出現次數 = **0**。
**違反處置**：直接砍該輸出 + 寫 incident report + 補測試（防回歸）。

### II. 引用接地 — Grounding（NON-NEGOTIABLE）

每一句結論、每一個數字都要能查到來源（法說稿頁碼 / 新聞 URL / 財報欄位）。
**沒來源就絕不輸出**——寧可說「資料不足」也不要瞎掰。

來源彼此矛盾時：
- 不要替使用者下結論
- 兩邊都列出來，標明矛盾在哪
- 讓使用者自己判斷

為什麼這條 NON-NEGOTIABLE：我們是**輔助工具**，不是預言家。
使用者要能驗證、能反駁、能追到底——做不到這點，這套系統就跟「會幻覺的 chatbot」沒兩樣。

### III. 雲端協作優先 · 金鑰安全

**雲端協作優先**（決策 Q-03，2026-06-02 更新）：開發預設後端＝**BigQuery 共用 canonical `polaris_core`**；個人實驗寫進自己的 `polaris_dev_<name>` scratch。
- 為什麼：100 份法說稿的 embedding **算一次、大家讀**，7 人共用同一份可信資料（省 token、資料一致），勝過 7 份各自的本地 DB
- **pgvector 不刪**：保留為離線 / Demo fallback（改一個 `VECTOR_BACKEND` env 即切回），維度 768 / cosine 兩端一致
- 做法見 `docs/開發環境_BigQuery.md` 與 `docs/協作開發環境_SOP_v1.md`

**金鑰絕對只放兩個地方**：本機 `.env` 或 GCP Secret Manager。
- ❌ 不准 commit、不准貼群組、不准丟 Drive、不准截圖到簡報（決策 Q-10）
- ✅ `.env` 已經 gitignore 了，自己別覆寫
- 萬一外洩：**立刻 revoke 重發**——光從 git 刪掉不夠，歷史還在、可能已被爬

### IV. Eval 即品質門檻

功能「好不好」**以分數為準，不以感覺為準**。
- 為什麼：「我覺得還不錯」沒法跨人比較、過閘門時翻車最丟臉
- 工具：Ragas（自動化）+ 三方 Judge（Claude Opus 4.7 / GPT-5 / Gemini 3 Pro 投票）

**硬門檻**（任一不達標 = G3 No-Go）：
- Context Precision ≥ 0.85
- Faithfulness ≥ 0.90
- Answer Relevance ≥ 0.85
- 130 題達標率 ≥ 80%

**Token 紀律**（防止 eval 把預算燒光）：
- 平常 CI：1 個便宜模型跑一次（Gemini 3 Flash）
- 閘門驗收：才動用三方 Judge

### V. Demo 可重現 + 離線備援

Demo Day 正餐跑**雲端**（Cloud Run + BigQuery + Vercel），但**必須有 Plan B**。

階梯式備援：
1. **Plan A**：雲端正常跑（首選）
2. **Plan B**：本機 pgvector + 同一份 demo（雲端斷網時切回）
3. **Plan C**：預錄影片（連本機都壞時的最後保險）

**承諾**：同一場景連跑 10 次結果一致；斷網切離線備援 **< 30 秒**。

### VI. 最新技術棧

技術選型已拍板，**不准用舊版 SDK**——舊版能跑但被標 deprecated，
未來會壞、晚換不如早換。

**Gemini**：
- ✅ 新版 SDK：`from google import genai; genai.Client()`
- ❌ 已淘汰：`google-generativeai` / `genai.configure`
- 模型：`gemini-3-pro-preview` / `gemini-3-flash-preview`
- 嵌入：`gemini-embedding-2`（多模態、768 維、cosine 距離）

**Rerank**：Cohere `client.v2.rerank`（model = `rerank-v4.0`）

例外處理：若某個版本確實不能用，在 PR 寫清楚理由，PM (R1) + Tech Lead (R2) 雙簽才能降版。

## Additional Constraints — 技術棧與成本

- **編排**：LangGraph（StateGraph）
- **檢索**：4-way（BM25 + 向量 + ColPali + Cohere Rerank）+ 新聞第 5 路
- **向量庫**：經 `VectorStore` 介面抽象
  - `VECTOR_BACKEND=bigquery`（**預設**，共用 canonical `polaris_core`）
  - `VECTOR_BACKEND=pgvector`（離線 / Demo fallback）
  - 維度 768、距離 cosine **兩端一致**，切換後跑同一份 eval 驗證
- **pgvector 查詢一定要用 `<=>`**（cosine 算子）
  - 用錯算子（`<->` 歐式 / `<#>` 內積）會全表掃描，速度跟 BigQuery 比差千倍
  - `ORDER BY embedding <=> $q LIMIT k` 才走 HNSW 索引
  - 詳見 `scripts/init_pgvector.sql` 註解
- **預算上限 ~$400 USD**
  - 大頭是 **LLM token**，不是 GCP infra（GCP 多數服務有免費額度）
  - 設預算警報
  - Embedding 算一次就重用、不重複呼叫
  - ColPali 模型試跑用 Colab / Kaggle 免費 GPU

## Development Workflow — Go / No-Go 閘

每個閘門過不了就**啟動降級方案，不硬撐**——避免硬撐到 Demo Day 翻車最丟臉。

- **G1 (Day 5)**：Ontology v1 凍結 + 100 份 PDF 入庫 **BigQuery `polaris_core`**
- **G2 (Day 10)**：e2e Workflow 跑通 + Ragas 管線上線（決策 Q-03 已定：BigQuery 為開發後端，pgvector 留 fallback）
- **G3 (Day 17)**：ColPali / LLMLingua 整合 + Eval ≥ 80% + Deep Research + Watchdog 可跑
- **G4 (Day 24)**：4 場景在**雲端**可重現 + 離線備援可切 + Watchdog 上線 + Eval ≥ 80%
- **Demo Day (Day 28)**：5 分鐘無斷點，斷網切預錄

降級方案見 PRD §5.4。

## Governance

本憲法**凌駕**所有其他實作慣例與口頭約定。

- 所有 PR 必須在 review 時確認**合規**，特別是 I、II、III 三條
- 修訂憲法：需經 **PM (R1) + Tech Lead (R2) 雙簽**，並記錄到 `01_PM_Notion匯入/決策追蹤.csv`
- 複雜度需要被正當化：加抽象、加 layer、加套件前要說清楚為什麼非加不可
- Runtime 開發指引見 repo `README.md` 與 `CLAUDE.md`

---

**Version**: 1.1.0 | **Ratified**: 2026-05-31 | **Last Amended**: 2026-06-02

> **v1.1.0（2026-06-02）**：原則 III「本地優先」→「雲端協作優先」（決策 Q-03 更新：開發預設後端改為 BigQuery 共用 canonical `polaris_core`，pgvector 保留為 fallback）；§Additional Constraints 向量庫預設、G1/G2 同步調整。**待 PM (R1) + Tech Lead (R2) 雙簽確認**（見 Governance；若認定為原則重定義，版號改 2.0.0）。
