# G1 架構面驗收自評（R2）

> **閘門**：W1 D5 G1（架構面）。本文是 R2 對「架構骨架是否就緒」的自評，
> 對應 `specs/001-langgraph-skeleton/spec.md` 的 FR/SC 與 R2 角色 spec 的 W1 交付。
> 每條都附**可重跑的證據**（測試名 / 指令），站會逐條過。

更新時間：2026-06-02 ｜ 全測試：`make check` → **110 passed, ruff clean**

## A. 架構面 Success Criteria

| 準則 | 內容 | 狀態 | 證據 |
|---|---|---|---|
| SC-001 | e2e 全程 0 人工介入產出 answer+citations | ✅ | `test_workflow_e2e.py::TestE2EHappyPath` |
| SC-002 | trace 完整列 5 節點、每個有 status | ✅ | `test_workflow_e2e.py::test_trace_has_all_five_nodes_in_order` |
| SC-003 | 6 關鍵字攔截率 100%、最終 answer 0 買賣建議 | ✅ | `test_compliance.py`、`test_writer_agent.py::test_llm_buysell_draft_still_blocked_by_compliance` |
| SC-004 | stub 模式 e2e < 10 秒 | ✅ | `test_workflow_e2e.py::TestE2ERuntime`（實測 <1s） |
| SC-005 | 換節點 → workflow.py diff = 0 行 | ✅ | `test_node_swap.py`（hash 不變） |
| SC-006 | 同問題 3 次 answer/citations 完全相同 | ✅ | `test_workflow_e2e.py::TestE2EDeterminism`（fallback 路徑確定性） |
| SC-007 | 空輸入只有 Planner 被執行、固定錯誤訊息 | ✅ | `test_workflow_edges.py` |

## B. R2 W1 交付（D1–D4）

| 交付 | 狀態 | 證據 |
|---|---|---|
| D1 5 節點 LangGraph 骨架 e2e | ✅ | `workflow.py` + e2e 測試 |
| D2 Planner Agent v0（拆步驟） | ✅ | `nodes/planner_agent.py`、`test_planner_agent.py`（LLM + fallback 雙路徑） |
| D3 Calculator + Writer v0 | ✅ | Writer：`nodes/writer_agent.py`（接地引用）；Calculator：確定性 v0（待 R4 資料） |
| D4 端到端縫合 + CLI | ✅ | `python -m polaris ask`／`python -m polaris.cli ask`（`test_cli.py`） |

**設計主軸**：smart node + 確定性 fallback —— 有真金鑰走 Gemini，否則確定性 fallback。
CI / 無金鑰開發 token=0；金鑰到位後零改碼即切真實呼叫。

## C. D5 金鑰閘門「GCP·Gemini key 全隊可用」

| 項目 | 狀態 | 說明 |
|---|---|---|
| 金鑰判斷修正 | ✅ | `is_real_key` 把空 / `#` 佔位視為未設定（修 truthy-placeholder bug） |
| 健檢工具 | ✅ | `make check-keys`／`python -m polaris doctor` 列出各金鑰 set/missing |
| 設定指南 | ✅ | `docs/keys-setup.md`（含 AI Studio 取金鑰步驟、安全守則） |
| **金鑰實際發到 7 人** | ⏳ 人工 | 每位成員自行在 `.env` 填**自己的** Gemini 金鑰；本機 `doctor` 目前 5 把皆 `missing`（佔位），需各自設定後轉 ✅ |

## D. 上游依賴（非 R2、待補才會「全綠」）

| 依賴 | 由誰 | 影響 |
|---|---|---|
| 真實檢索（contexts） | R4 | 目前 retriever 回 1 條 stub context；Writer 已能接地，換真資料即可 |
| 真實財務計算 | R4 | Calculator v0 為固定值，待結構化資料 |
| 各節點真 agent 細實作 | R3 | 介面已固定（stubs 為綁定層），R3 換實作不動 workflow.py |
| GitHub collaborator 接受邀請 | R3/R4/R5 | 3 人 pending，接受後才能推 branch（D2/D3 交接前置） |

## E. G1 結論（R2 視角）

**架構骨架就緒**：5 節點 e2e、節點可換、確定性、合規攔截、空輸入守門、CLI 進入點、金鑰健檢全部到位且有測試背書（110 passed）。
**唯一非綠**：金鑰需各成員自行設定（工具與文件已備齊）、上游 R3/R4 真實作待接（介面已固定）。建議 G1 判定為 **Go（架構面）**，並把「金鑰全員設定」「3 人接受 GitHub 邀請」列為 G1 出場 action item。
