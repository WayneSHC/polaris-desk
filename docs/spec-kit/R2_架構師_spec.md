# 角色規格書（Spec Kit）：R2 — AI 架構師 · Tech Lead

**Role**: R2 LangGraph 編排 + Deep Research Agent + 上雲 **色**：深藍
**對應**：專題 spec FR-003/004/007/008；4 週計畫 R2 卡 **Status**: Draft

## 1. Mission
把 5 步驟 Workflow 的骨架搭起來並逐步變聰明（時間定位 / retry / 壓縮 / 合規）；W3 做出第一個真 Agent（Deep Research）；W4 主導系統上雲。
- **In scope**：LangGraph 編排與狀態、Deep Research Agent、Temporal Anchoring、retry、LLMLingua、Compliance 節點、雲端部署架構、技術選型拍板（Q-03 / AQ-03 / AQ-08 協同）。
- **Out of scope**：各節點細部實作（R3）、資料 ingestion（R4）、評分（R5）。

## 2. Deliverables & Acceptance Criteria

| 交付物 | 對應 | 可驗收標準（measurable）|
|---|---|---|
| 5 節點 LangGraph 端到端 | G1/G2 | Planner→Retriever→Calculator→Writer→Compliance 串通，問題進、**帶引用答案出** |
| Temporal Anchoring | FR-007 | 「最近兩季 / 2024 全年」能正確解析並只取對應期間資料 |
| retry + LLMLingua | SC-006 | 任一節點失敗自動重試；LLMLingua 量到 **token 省 ≥ 50%** |
| Deep Research Agent v1 | FR-004 | 對驗收題（場景 2）**≤ 6 次 ReAct 迴圈**內產出含 **≥ 3 條引用**的結論、**句句可溯源、0 買賣建議** |
| 系統上雲 | SC-004/G4 | Day 20–22 後端上 Cloud Run、切 BigQuery 後端、金鑰進 Secret Manager；**G4 在雲端驗收 4 場景可重現** |

## 3. Tasks by Week（可勾選）

**W1**
- [x] D1 LangGraph 骨架：5 空節點、每節點先回假資料
- [x] D2 Planner Agent v0：把問題拆成步驟 — `nodes/planner_agent.py`（Gemini Flash + 確定性 fallback）
- [x] D3 Calculator + Writer v0 — Writer `nodes/writer_agent.py`（接地引用）；Calculator 確定性 v0（待 R4 資料）
- [x] D4 LangGraph 縫合：端到端跑一次 — `python -m polaris ask` / `python -m polaris.cli ask`（114 tests green）
- [~] D5 G1 驗收（架構面）／GCP·Gemini key 全隊可用 — 工具/文件就緒（`make check-keys`、`docs/keys-setup.md`、`docs/G1_readiness.md`）；**待全員自填金鑰 + 站會過閘**

**W2**
- [ ] D6 Temporal Anchoring
- [ ] D7 LangGraph retry
- [ ] D8 LLMLingua POC（量 token 省幅）
- [ ] D9 Compliance Agent 節點接入
- [ ] D10 G2 驗收（架構面）／協同 R4 跑 **BigQuery 煙測（Q-03）**

**W3（+2 人天）**
- [ ] D11 LangGraph 狀態管理
- [ ] D13 Agent prompt 優化
- [ ] D15 Deep Research v0：ReAct loop 跑通
- [ ] D16 Deep Research v1：過驗收（≤6 迴圈 / ≥3 引用 / 可溯源）
- [ ] D17 G3 評審

**W4**
- [ ] D20–22 **系統上雲**：Cloud Run + BigQuery 後端 + Secret Manager（與 R7 前端 Vercel 對接）
- [ ] D19–20 供部落格 1（Workflow vs Agent）、2（Deep Research）技術內容
- [ ] D24 G4：確保 4 場景**在雲端**可重現
- [ ] D25–27 彩排技術待命

## 4. Dependencies
- **上游**：R3（各節點 / agent 細實作）、R4（資料接口 / BigQuery store / 事件來源）、R7（前端對接）。
- **下游**：R3 的節點都掛在你的 LangGraph 上；R5 的 CI 接你的 e2e；R7 上雲要你的後端先就緒。

## 5. Risks & Fallback
- Deep Research 不穩 → 先確保 v0 ReAct loop 跑通；v1 行為不穩時收斂迴圈上限。
- 第一次上雲踩坑 → **不留到 Demo 前夜**：Day 10 先 BigQuery 煙測、Day 20–22 真部署，留 buffer。

## 6. Constitution 遵循
- 守 **VI**：Gemini 用 `google-genai` 新 SDK + `gemini-3-*-preview`；嵌入 `gemini-embedding-2`。
- 守 **III**：金鑰走 Secret Manager / `.env`，部署腳本不得硬寫金鑰。
- Compliance 節點落實 **I（NFR-031）**：輸出前攔截買賣建議。
