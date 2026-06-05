# 自己寫一個 ReAct Agent：Polaris Desk Deep Research 的設計

> Polaris Desk 技術部落格 · 系列 (2/2)
> 對應 R2 spec D19–20；技術細節對照 `src/polaris/graph/deep_research/`。

系列第 1 篇談了「哪一段該用 agent」。這篇深入其中一個 agent——**Deep Research**——講三件事：為什麼**自己寫** ReAct loop、怎麼用**硬邊界**馴服自主性、以及怎麼確保結論**句句可溯源、0 買賣建議**。

## 抉擇 AQ-03：為什麼不用 prebuilt `create_react_agent`

LangGraph 有現成的 `create_react_agent`，照理說該直接用。我們查了現行文件後選擇**自己寫**，理由三條：

1. **它已被標 deprecated**——押注一個正在淘汰的 API 不划算。
2. **它綁 LangChain chat model 抽象**（要多裝 `langchain-google-genai` / `ChatGoogleGenerativeAI`），跟我們整個專案用的 **raw `google-genai`** smart-node 模式不一致。我們的每個節點都是「有金鑰走 Gemini、無金鑰走確定性 fallback」，prebuilt 進來會割裂這個一致性。
3. **我們要顯式控制邊界**：≤ 6 迴圈、≥ 3 引用、整合既有 `@traced` 與 Compliance 閘。這些用自寫 loop 編碼最直接。

自寫的成本其實很低——ReAct 的核心就是一個 bounded 迴圈。換來的是 token-free 可測、無 deprecation 風險、與全專案一致。

## ReAct loop 的骨架：reason → act → observe

一個 ReAct step 就是三件事，我們把它定成 pydantic 模型（`state.py`）：

```python
class ReActStep(BaseModel):
    thought: str          # 想：現在該做什麼
    action: str           # 做：search / finish
    action_input: str = ""
    observation: str = "" # 觀察：查到什麼
```

loop 本體（`agent.py` 的 `run_deep_research`）就是反覆 reason→act→observe，直到 agent 自己說 finish 或撞到上限。**有金鑰**時走 Gemini（`build_react_prompt` → `generate` → `parse_react_action`，外面包 D7 retry）；**無金鑰**時走確定性 facet 政策（營收/毛利率/風險輪流查到湊滿 ≥3 條才 finish）。

## 馴服自主性：三道硬邊界

自主 agent 最怕「跑不停」「亂回答」。我們用三道編碼在程式裡的邊界（不是寫在 prompt 裡求 LLM 自律）：

### 邊界 1：≤ 6 迴圈（FR-004）
`should_continue` 是純函式，status 標 answered 或 iteration 撞上限就停：

```python
def should_continue(state, *, max_loops: int = 6) -> bool:
    ...  # status == "answered" 或 iteration >= max_loops → 停
```

硬上限直接編碼，LLM 無從繞過。跑滿 6 圈仍沒結論 → status 標 `exhausted`，誠實回報而非硬掰。

### 邊界 2：≥ 3 條可溯源引用
`evidence` 依 `source_id` **去重累積**，湊不到 3 條不准 finish。這擋掉「查一條就妄下結論」。

### 邊界 3：解析失敗安全退場
LLM 偶爾會吐出格式壞掉的 Action。`parse_react_action` 對**格式錯誤 / 空輸出一律安全退回 `finish`**——意思是 loop **必定終止**，不會因為一次壞輸出就卡死或無窮迴圈。

## D16：verify-or-synthesize——接地 > 文采

光是「有引用」不夠，我們要的是**每一句論點都掛得回證據**。`state.is_fully_traceable(answer, evidence)` 檢查每條列點是否帶 `（來源：sid）` 且該 sid 真的在 evidence 裡。

關鍵設計在 `_synthesize`：它**逐點結構化**——一條 evidence 配一個 bullet、各自帶來源——所以結論**天生句句可溯源**（by construction），而不是事後檢查。

更狠的是 v1 的硬保證：**候選答案（包含 LLM 自由發揮的文字）如果不可溯源、但手上有 evidence，就直接換成結構化的 grounded 版本**。我們明確選擇 **接地 > 文采**：LLM 的推理過程仍完整保留在 `react_steps` 裡可供檢視，但對外結論一定踩在證據上。

## 韌性：fail-to-deterministic

LLM 會抖、會掛、會超時。Deep Research 的每個 LLM 邊界都包了 D7 的 `call_with_retry`（暫時性錯誤指數退避重試），**重試用盡仍失敗就退回確定性 facet 政策**——agent 照樣跑完、照樣產出可溯源結論，只是少了 LLM 的靈活。**功能不會因為 Gemini 打嗝就掛掉。**

## 合規：最後一道，誰都不能跳過

Deep Research 的最終結論**和主 workflow 走同一道 Compliance 閘**（NFR-031）。`_synthesize` 本身不產買賣建議，最終答案再過一次合規攔截。自主 agent 的開放性不會變成繞過合規的破口。

## 一個讓 CI 不花錢的小設計：注入式 search

`run_deep_research(question, *, search=stub_search, ...)` 的 `search` 是**注入式 seam**。預設 `stub_search` 是 token-free 的假檢索，CI 拿它端到端驗 loop 行為（bounded、≥3、NFR-031 攔截、LLM 退確定性）全不花 token。等 R4 的真實 `VectorStore.search` 就緒，**換一個參數**就接上真檢索，loop 本體一行不改。

## 驗收：場景 2 的四道門檻

對同業比較題「比較台積電與聯發科最近兩季毛利率變化」，我們斷言四件事全過、且可重現：**≤ 6 迴圈、≥ 3 條引用、句句可溯源、0 買賣建議**。這四條由 `test_deep_research_acceptance.py` 背書，每次 CI 都跑。

---

**小結**：一個好用的 agent，自主性要花在刀口上，其餘全用工程紀律框住——硬上限、去重門檻、安全退場、接地優先、fail-to-deterministic、共用合規閘。自由與可靠不是二選一，是用邊界設計把兩者一起拿到。
