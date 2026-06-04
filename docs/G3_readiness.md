# G3 架構面驗收自評（R2）

> **閘門**：W3 D17 G3（架構面）。本文是 R2 對「W3 第一個真 Agent（Deep Research）是否就緒 +
> R2 在 G3 四條件的對應交付」的自評，對應 spec 的 FR-004 / SC 與 R2 角色 spec 的 W3 交付（D11–D16）。
> 每條都附**可重跑的證據**（測試名 / 指令）。
>
> **G3 四條件**（`00_Polaris-Desk_專題_spec.md` §閘門表）：**ColPali/LLMLingua 整合 + Eval ≥ 80% +
> Deep Research 可跑 + Watchdog 可跑**（ColPali 失敗 → 砍場景 3 + ColPali）。其中 **R2 直接負責**＝
> Deep Research 可跑、以及 LLMLingua 的**量測**半邊；Eval ≥ 80%＝R5、ColPali＝R6、Watchdog＝R3。
> 四條件逐項 owner 簽核的**完整驗收清單＝R1 的卡**（R1 spec D15–16），本文不越界。

更新時間：2026-06-04 ｜ 全測試：`make lint && make test` → **304 passed, ruff clean**
｜ 開發路徑：`~/code/polaris-desk`（已移出 iCloud 同步，見專案記憶事故註記）

## A. G3 四條件 × R2 對應狀態

| G3 條件 | owner | R2 視角狀態 | 證據 / 備註 |
|---|---|---|---|
| **Deep Research 可跑** | **R2** | ✅ | v0 loop 跑通（D15）+ v1 過驗收（D16）；見 §C 場景 2 四門檻 |
| **LLMLingua** 整合 | **R2**（量測）/ 全隊（整合決策）| ◐ | 量測 harness ✅、確定性基線實量 ~7–14%；**≥50% 實測待本機 `[llmlingua]` extra**（§E action item）。**刻意「量測 only、未接進 live graph」**（D8：避免未測品質就動 retriever→writer 影響接地）|
| ColPali 整合 | R6 | ⤷ 跨角色 | POC 待 R6；**若失敗 → 砍場景 3 + ColPali**（spec 已定）。不影響 R2 Deep Research |
| Eval ≥ 80% | R5 | ⤷ 跨角色 | 130 題 Ragas + 三方 Judge（CP≥0.85 / Faithfulness≥0.90 / AR≥0.85）；R5 spec D17 公布分數 |
| Watchdog 可跑 | R3 | ⤷ 跨角色 | 事件 Watchdog Agent 待 R3 |

## B. R2 W3 架構面交付（D11–D16，皆已併入 main）

| 交付 | 對應 | 狀態 | 證據（可重跑）|
|---|---|---|---|
| D11 狀態管理 / AQ-03 拍板 | FR-004 | ✅ | 設計文件 `specs/2026-06-03-r2-w3-d11-...-state-design.md`；決策＝**自寫 ReAct loop**（棄 deprecated `create_react_agent`）；狀態模型於 D15 落地 |
| D13 Agent prompt 優化 | FR-004 | ✅ | `test_prompts.py`、`test_deep_research_react.py`；中央 registry `graph/prompts.py`（`NO_ADVICE_CLAUSE` single source）+ ReAct 機制 `graph/deep_research/react.py` |
| D15 Deep Research v0（loop 跑通）| FR-004 | ✅ | `test_deep_research_state.py`、`test_deep_research_agent.py`；純 Python bounded loop（reason→act→observe），evidence 去重累積，最終過 D9 Compliance |
| D16 Deep Research v1（過驗收）| FR-004 | ✅ | `test_deep_research_acceptance.py`（PR #27, b495cfb）；`is_fully_traceable` + verify-or-synthesize 硬保證 |

## C. Deep Research v1 驗收證據（場景 2：同業比較）

驗收題：「比較台積電與聯發科最近兩季的毛利率變化」。`test_deep_research_acceptance.py::TestAcceptanceScenario2`
對 `run_deep_research(...)` 斷言四門檻全過、且**可重現**（同輸入兩跑 final_answer / iterations 完全相同）：

| FR-004 門檻 | 斷言 | 機制 |
|---|---|---|
| ≤ 6 次 ReAct 迴圈 | `iterations <= 6` | `should_continue(max_loops=6)` 硬編碼上限 |
| ≥ 3 條引用 | `len(evidence) >= 3` | 確定性 facet 政策（營收/毛利率/風險）輪流 search 到 ≥3 才 finish；依 source_id 去重 |
| 句句可溯源 | `is_fully_traceable(answer, evidence)` | `_synthesize` 逐點結構化（一 evidence 一 bullet+`（來源：sid）`）→ by construction；v1 verify-or-synthesize 硬保證（LLM 自由文未可溯源 + 有 evidence → 換結構化 grounded）|
| 0 買賣建議 | `all(kw not in answer for kw in BUYSELL_KEYWORDS)` | 最終結論一律過 **D9 Compliance Agent**（NFR-031） |

> 場景 2 期望輸出的「並列數字表」需 **R4 真實財務資料** → stub 階段不做（pending R4）；
> 但 **≤6 / ≥3 / 可溯源 / 0 建議** 四門檻以 stub evidence 即可達成並已驗收。

## D. 核心不變量（W1 起持續綠）

| 準則 | 內容 | 狀態 | 證據 |
|---|---|---|---|
| SC-001/002 | e2e 0 介入產出 answer+citations、trace 列 5 節點 | ✅ | `test_workflow_e2e.py` |
| SC-003 | 6 關鍵字攔截 100%、最終 answer 0 買賣建議 | ✅ | `test_compliance.py`、`test_compliance_agent.py`；Deep Research 最終結論亦過 D9（`test_deep_research_agent.py`）|
| SC-005 | 換節點 → workflow.py diff = 0 行 | ✅ | `test_node_swap.py`（hash 不變；D11–D16 僅新增 `graph/deep_research/` + `graph/prompts.py`、`workflow.py`/`state.py`(5節點)/`compliance.py` 未動）|
| SC-006 | 同問題 3 次結果完全相同 | ✅ | `test_workflow_e2e.py::TestE2EDeterminism`；Deep Research 亦可重現（§C `test_repeatable`）|
| SC-007 | 空輸入只跑 Planner、固定錯誤訊息 | ✅ | `test_workflow_edges.py` |

## E. 上游依賴 / Action items（待補才會「全綠」）

| 項目 | 由誰 | 影響 |
|---|---|---|
| LLMLingua ≥50% 實測 | R2（本機）| `uv pip install -e '.[llmlingua]'`（torch，刻意不進 CI）+ 跑 `python -m polaris.compression`，回填 D8 設計文件 §6。**G3 LLMLingua 半邊收尾** |
| Eval ≥ 80%（130 題 Ragas + 三方 Judge）| R5 | **G3 硬門檻**；R5 spec D17 公布分數。卡關 < 80% 啟動降級（砍場景 3）|
| ColPali POC | R6 | G3 條件；**失敗 → 砍場景 3 + ColPali**（spec 已定 contingency）。不阻擋 R2 Deep Research |
| Watchdog Agent 可跑 | R3 | G3 條件（第 2 個 Agent）|
| 真實「入庫資料」BigQuery 煙測（Q-03）/ `BigQueryStore.{health_check,add_documents,search}` | R4 | 沿用 G2 未關項；R4 ingestion（SOP §4）尚未開工。R2 **未碰**該檔（角色邊界）|
| 全員 `GCP_PROJECT=polaris-desk-team` + ADC 金鑰 | 各成員 | 沿用 G2；否則 bq-smoke config fail / connectivity skipped |
| 金鑰全員到位 + G1 站會過閘（D5 `[~]`）| 全員 | G1 出場 action item 尚未關閉 |

## F. G3 結論（R2 視角）

**R2 架構面就緒 → Go（架構面）**：第一個真 Agent（Deep Research）v0 跑通、v1 **過驗收**
（場景 2 四門檻全過且可重現，`test_deep_research_acceptance.py` 背書），W3 交付 D11/D13/D15/D16 全綠、
5 節點 e2e / 節點可換 / 確定性 / 合規攔截等核心不變量持續綠（**304 passed, ruff clean**）。

**R2 半邊未收尾（非阻塞、非架構碼問題）**：LLMLingua **≥50% 實測**待本機 `[llmlingua]` extra 跑真 backend
（量測 harness 已就緒、基線已實量；且 D8 刻意「量測 only、未接進 live graph」）。

**整體 G3 是否過閘取決於跨角色硬門檻**：Eval ≥ 80%（R5）、ColPali（R6，失敗則砍場景 3）、Watchdog（R3）。
建議 **R1 彙整 4 條件逐項 owner 簽核**（R1 spec D15–16）作為 G3 最終裁定；R2 在此確認**架構面與 Deep Research 端**已備妥。
