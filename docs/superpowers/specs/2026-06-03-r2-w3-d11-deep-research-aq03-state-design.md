# R2 W3 D11 — Deep Research Agent：AQ-03 框架決策 + 狀態設計

**日期**：2026-06-03 ｜ **角色**：R2 AI 架構師（施惠棋 / WayneSHC）
**對應**：FR-004（系統含 2 真 Agent：Deep Research(ReAct loop) + Watchdog）、Deep Research v1 驗收（**≤ 6 ReAct 迴圈 / ≥ 3 引用 / 句句可溯源 / 0 買賣建議**）、**AQ-03**（Deep Research 框架選型，Day 14，R2）、R2 spec §3 W3 D11
**性質**：決策 + 設計文件（**本輪不寫 code**；ReAct loop 實作於 D15、狀態模型於 D15 以 TDD 落地）
**前置**：D6–D10（已併入 main）、D9 Compliance Agent、D7 retry primitive、smart-node + 確定性 fallback 架構

---

## 1. 目的

W3 要做出**第一個真 Agent — Deep Research（ReAct loop）**。D11 先把兩件 D15 的地基定下來：
1. **AQ-03**：選定 Deep Research 框架（Day 14 到期、R2 拍板）。
2. **狀態管理**：設計 Deep Research 的狀態模型 + 迴圈停止邏輯（直接編碼 FR-004 驗收）。

---

## 2. AQ-03 — 框架決策

### 候選與評比
| 候選 | 評估 | 結論 |
|---|---|---|
| **LangGraph prebuilt `create_react_agent`** | 程式最少；但：① 現行 LangGraph reference 標其 **deprecated**（prebuilt agent 正被新 API 取代）；② 它走 **LangChain chat model 抽象**（`model="provider:model"` 或 `ChatModel`，靠 `bind_tools` + messages），需引入 `langchain-google-genai`／`ChatGoogleGenerativeAI` 這條新依賴，與本專案 **raw `google-genai` `GeminiClient`**（`.generate(prompt, flash=, system_instruction=)`）的 smart-node + 確定性 fallback 不一致；③ message-scratchpad 讓「CI 確定性 fallback」與「≤6/≥3/逐句接地」的嚴格控制變得彆扭。 | ❌ 棄（deprecated + 架構不一致）|
| **LangChain `AgentExecutor`** | 更舊、更重，同樣綁 LangChain model/tools 抽象，且正被取代。 | ❌ 棄 |
| **自寫 ReAct loop（以 LangGraph subgraph 編排）** | 重用 `active_llm()`/`GeminiClient`（**零新 LLM 依賴**、同 smart-node 模式）；可給**確定性 fallback** ReAct（無金鑰回 stub 證據 → CI token-free）；**顯式 iteration 計數**控 FR-004 的 ≤6 迴圈、**evidence 累積**達 ≥3；整合既有 `@traced` + D9 Compliance Agent；自己掌握驗收關鍵控制流、**無 deprecation 風險**。代價：比 prebuilt 多寫一點 code，但量小且控制權在我們手上。 | ✅ **採用** |

### 決策
**自寫 ReAct loop，以 LangGraph subgraph 編排。**

- **LLM**：重用 `polaris.llm.gemini.active_llm()`；有金鑰走 Gemini（規劃/反思用 Flash、必要時 Pro），無金鑰走**確定性 fallback ReAct**（固定步數、回 stub 證據）→ CI / 無金鑰皆可跑、token=0。
- **工具（tools）**：v0 先接既有 retriever / `VectorStore.search`（接地引用來源）；Deep Research 真正的網路搜尋（Tavily）於後續迭代接入（依賴已在 pyproject：`tavily-python`）。
- **編排**：用 LangGraph `StateGraph` 組一個 **Deep Research subgraph**（`reason → act → observe → (should_continue?) ↺ / → finalize`），與現有 5 節點主圖**分離**（不動 `workflow.py`/`ResearchState`，node_swap 不變）。
- **合規**：最終結論在輸出前仍過 **D9 Compliance Agent `review()`**（NFR-031；ReAct 中途思考不外洩）。
- **retry**：對 Gemini 呼叫沿用 D7 `call_with_retry`（暫時性錯誤重試、fail-to-fallback）。

---

## 3. 狀態設計（D15 實作；本節定契約）

新模組（暫定 `polaris/graph/deep_research/state.py`），**不**動 `ResearchState`/`workflow.py`。

### 型別
```python
class ReActStep(BaseModel):           # frozen
    thought: str
    action: str                       # 例 "search" | "finish"
    action_input: str = ""
    observation: str = ""             # 工具回傳摘要

class DeepResearchState(TypedDict, total=False):
    question: str
    iteration: int                                        # ReAct 迴圈計數
    react_steps: Annotated[list[ReActStep], operator.add] # append reducer（逐步審計/可溯源）
    evidence: Annotated[list[Citation], add_dedup]        # 跨迴圈累積引用（依 source_id 去重）→ ≥3
    final_answer: str
    status: Literal["running", "answered", "exhausted"]
```
- `react_steps` 用 `operator.add` append（與主圖 `trace` 同模式）→ 完整保留每一輪 thought/action/observation，滿足「**句句可溯源**」的審計需求。
- `evidence` 用**去重累積** reducer（依 `Citation.source_id`）→ 多輪檢索的引用不被覆蓋、自然累積到 ≥3。

### 迴圈停止邏輯（驗收關鍵純函式）
```python
def should_continue(state, *, max_loops: int = 6, min_citations: int = 3) -> bool:
    if state.get("status") == "answered":
        return False
    if state.get("iteration", 0) >= max_loops:   # FR-004 硬上限：≤6 迴圈
        return False
    return True
```
- **硬上限 `max_loops=6`** 直接編碼 FR-004「≤ 6 次 ReAct 迴圈」；到頂強制收斂（status→`exhausted`，輸出目前最佳結論 + 誠實標註證據不足）。
- **`min_citations=3`**：finalize 時若 `len(dedup(evidence)) < 3`，明標「引用不足、結論暫定」（不假裝達標——對齊憲法「不臆測」）。
- 純函式、無 I/O → D15 可單測各邊界（0/中途/第6輪/已答）。

### 與既有契約的關係
- 不改 `ResearchState`/`workflow.py`/`compliance.py` → `test_node_swap` + 5 節點 trace 不變。
- Deep Research subgraph 可獨立 invoke，也可（後續）作為主圖一個節點掛入（介面預留）。

---

## 4. 範圍邊界

- **本輪（D11）**：只交付本決策 + 狀態設計文件、勾 spec、同步 AQ-03 決策 CSV。**無 src/test 變更。**
- **D13**：Agent prompt 優化（ReAct system prompt / 工具描述）。
- **D15**：以 TDD 實作 ReAct loop + 上述狀態模型 + `should_continue` + 確定性 fallback。
- **D16**：過驗收（≤6 / ≥3 / 可溯源 / 0 買賣建議）。
- **Watchdog Agent（FR-004 第 2 個 Agent）**：不在 R2 W3 卡片內（另角色 / 後續）。

---

## 5. Constitution 遵循

- **VI**：Gemini 走 `google-genai`（`active_llm()`）；**不**為了 prebuilt 而引入 LangChain model 依賴。
- **III**：金鑰沿用 `active_llm()`；無新增金鑰路徑。
- **I（NFR-031）**：最終結論過 D9 Compliance Agent；ReAct 中途思考不外洩成輸出。
- **成本紀律**：無金鑰 → 確定性 fallback ReAct，CI token=0。

---

## 6. 交付物

本設計文件 · R2 spec D11 → `[x]`（repo + Drive mirror）· 決策追蹤 CSV **AQ-03 → 已決** · 專案記憶更新 · PR + admin-merge。**無程式碼變更**（實作 D15）。
