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
- [x] D6 Temporal Anchoring — `graph/temporal.py`：最近N季 / YYYY全年 / YYYYQn / YYYY年第n季 → 季別清單；planner 寫 `state['period']`、retriever 依季別過濾（未入庫季別→誠實回「資料不足」）
- [x] D7 LangGraph retry — `retry.py` 通用 primitive（`is_transient` 分類 + exponential backoff）；Tier 1 套 LLM 邊界（make_plan/make_draft：暫時性 429/5xx/timeout 重試後恢復才保住 LLM 答案，持續/永久才降級 fallback）；Tier 2 `@traced(retries=)` 節點保險絲（retriever/calculator=2，R4 接真實 I/O 用），用盡仍守 FR-009（error trace + halt）
- [x] D8 LLMLingua POC（量 token 省幅）— `compression/`：`tokens.py`（tiktoken + regex fallback token 計數）、`compressors.py`（Compressor 介面 + 確定性基線 + LLMLingua 選用 backend，鏡像 `active_llm()` smart-node 模式）、`measure.py`（量測 harness，重用 writer 攤平邏輯）；`python -m polaris.compression` runner 實量確定性基線省 ~7–14%（誠實，不 game 假語料）；≥50% 由本機 `[llmlingua]` extra 跑真 backend 產生、零結構改動。量測 only，**未**接進 live graph（避免未測品質就動 retriever→writer 影響接地）
- [x] D9 Compliance Agent 節點接入 — `nodes/compliance_agent.py`：6 關鍵字確定性 floor（`apply_compliance`，永遠先跑、命中即收、LLM 永不解除）+ Gemini Flash smart 層（補抓關鍵字外的隱性建議：進場時機/逢低布局/值得擁有）；**fail-to-floor**（LLM 任何失敗用 D7 retry 撐過後仍失敗則退回 floor，絕不弱化保證）；LLM 只回 verdict、**永不改寫** draft（攔截恆回 SAFE_MESSAGE，SC-003 不破）。`stubs.compliance` 委派 review、輸出契約不變；無金鑰（CI）=floor-only=W1 行為一致。`BUYSELL_KEYWORDS` 仍鎖 6 條（lexicon/紅隊擴充＝R6 W3）。`workflow/state/compliance.py` 不動（node_swap + 5 節點 trace 不變）
- [~] D10 G2 驗收（架構面）／協同 R4 跑 **BigQuery 煙測（Q-03）** — **架構面已完成**：`docs/G2_readiness.md` 自評（D6–D9 全綠 + 核心不變量，249 passed）；上雲「管路」煙測 harness `diagnostics.bigquery_smoke` + `python -m polaris bq-smoke` / `make bq-smoke`（`test_bq_smoke.py` 背書），把 R4 未實作的 `health_check` 歸 pending、無金鑰歸 skipped，**零接觸 R4 檔、R4 補完即零改碼轉真**。⏳ **完整版待 R4**：真連線 + 入庫資料煙測需 R4 ingestion（SOP §4，尚未開工）；另各成員待設 `GCP_PROJECT`/ADC 金鑰

**W3（+2 人天）**
- [x] D11 LangGraph 狀態管理 — **AQ-03 拍板（早於 Day 14）＝自寫 ReAct loop（LangGraph subgraph 編排）**，棄 prebuilt `create_react_agent`（已 deprecated + 需 LangChain chat model 新依賴、與 raw google-genai `GeminiClient` smart-node 不一致）。設計 Deep Research 狀態模型：`ReActStep`、`iteration`、`react_steps`（append reducer，可溯源）、`evidence`（依 source_id 去重累積，≥3）、純函式 `should_continue`（硬上限 ≤6 迴圈，直接編碼 FR-004）。不動 `ResearchState`/`workflow.py`（node_swap 不變）。設計文件 `docs/superpowers/specs/2026-06-03-r2-w3-d11-deep-research-aq03-state-design.md`；**ReAct loop + 狀態以 TDD 實作於 D15**
- [x] D13 Agent prompt 優化 — ① 中央 prompt registry `graph/prompts.py`：共用片段 `NO_ADVICE_CLAUSE`（NFR-031 single source）/`GROUNDING_CLAUSE`，組裝 PLANNER/WRITER/COMPLIANCE/REACT system prompt；planner/writer/compliance 改 import + 重新導出（零行為變更，測試全過）。② Deep Research ReAct 機制 `graph/deep_research/react.py`：`REACT_SYSTEM_PROMPT`、`ReActTool`/`DEFAULT_TOOLS`(search/finish)/`render_tools`、`build_react_prompt`（工具+scratchpad+問題）、`parse_react_action`（解析 Action/Action Input，格式錯誤安全退 finish）。測試含「生成型 prompt 皆含 NO_ADVICE_CLAUSE」不變量。workflow/state 不動；loop 本體 D15 實作
- [x] D15 Deep Research v0：ReAct loop 跑通 — `graph/deep_research/`：`state.py`（`ReActStep`、`dedup_evidence` 依 source_id 去重累積、`should_continue` 硬上限 ≤6、`DeepResearchResult`）、`agent.py`（`run_deep_research` 純 Python bounded loop：reason→act→observe；smart 走 Gemini+D7 retry / 無金鑰走確定性 facet 政策；LLM 失敗 fail-to-deterministic；`stub_search` token-free seam，R4 真實檢索之後接這）。最終結論一律過 **D9 Compliance**（NFR-031）；`_synthesize` 不產買賣建議。消費 D13 `react.py`。不動 workflow/state(5節點)/compliance。23 新測（state 11+agent 12，含 NFR-031 攔截、bounded、LLM 退確定性）。嚴格驗收（≤6/≥3/可溯源/0 建議）＝D16
- [x] D16 Deep Research v1：過驗收（≤6 迴圈 / ≥3 引用 / 可溯源）— 對場景 2 同業比較題（「比較台積電與聯發科最近兩季毛利率變化」）斷言四門檻全過。新增 `state.is_fully_traceable(answer, evidence)`（每條列論點須帶 `（來源：sid）` 且 sid∈evidence）；`_synthesize` 改逐點結構化（一 evidence 一 bullet+來源 → 句句可溯源 by construction）；**v1 硬保證 verify-or-synthesize**：候選答案（含 LLM 自由文）未可溯源且有 evidence → 換結構化 grounded（接地>文采，LLM 推理仍存 react_steps）；gated on evidence 不破無證據測試。8 新測。場景 2「並列數字表」待 R4 真實財務資料。不動 workflow/state(5節點)/compliance
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
