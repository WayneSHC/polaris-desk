# R2 W2 D7 — LangGraph Retry 設計

- **日期**：2026-06-03
- **負責人**：R2（AI 架構師 / Tech Lead）
- **對應 spec**：`docs/spec-kit/R2_架構師_spec.md` W2 D7「LangGraph retry — 任一節點失敗自動重試」
- **驗收**：SC-006「任一節點失敗自動重試」
- **前置**：W1 D2–D5（真 Planner/Writer 節點 + smart-node/fallback）、W2 D6（Temporal Anchoring）已併入 main。

## 1. 背景與問題

現行「smart node + 確定性 fallback」架構下：

- `make_plan` / `make_draft`：`if client: try llm except Exception: → fallback`。
  → Gemini **任何一次** 暫時性失敗（429 / 5xx / timeout）就**立刻**掉到確定性
  fallback（降級答案），**沒有重試**。一個網路抖動就讓我們白白丟掉高品質 LLM 答案。
- `@traced` 裝飾器：節點丟例外 → error trace + `halt=True` → 路由到 terminal。
  目前節點幾乎不會丟例外（LLM 失敗被 fallback 吞掉；只有 planner 的空字串
  `ValueError("empty query")` 會丟，而那是**永久性**錯誤、不該重試）。

**結論**：retry 真正有價值、且今天就會觸發的地方是 **LLM 呼叫邊界** ——
暫時性錯誤重試幾次，撐過抖動就保住 LLM 答案，持續失敗才降級 fallback。
節點層 retry 則是**未來保險絲**（R4 接真實向量檢索 / BigQuery 後，節點才會有
真正的 I/O 暫時性失敗）。

## 2. 設計總則

一個純粹、可重用的 retry primitive，套在兩個層級。**Graph wiring（`workflow.py`）
完全不動** —— retry 住在節點實作層與 `@traced` 裝飾器，因此 FR-007 / SC-005
與 `test_node_swap` 的 hash invariance 檢查都不受影響。

### 2.1 新模組 `src/polaris/retry.py`（通用，零 LLM / graph 耦合）

```python
def is_transient(exc: BaseException) -> bool: ...
def default_sleep(seconds: float) -> None: ...   # time.sleep 的間接層，測試可 null 掉
def call_with_retry(
    fn, *, attempts=3, base_delay=0.5, max_delay=8.0,
    retry_on=is_transient, sleep=None,
): ...
```

- **`is_transient(exc)`** — 啟發式分類：
  - `True`：狀態碼（讀 `.code` / `.status_code` / `.status`）∈ `{408,409,425,429,500,502,503,504}`；
    或 type 名稱含 `timeout / unavailable / servererror / deadline / connection / temporar`。
  - `False`：其餘一律（含 **`ValueError`**「empty query」、永久性 4xx）→ **不重試**。
- **`call_with_retry(fn, ...)`** — 跑 `fn()`；遇到「可重試」例外就 exponential
  backoff 後重試；attempts 用盡或例外不可重試 → re-raise 最後一個例外。
  `sleep` 經 `default_sleep` 間接呼叫，測試可注入 no-op → 快速、確定、token=0。
  backoff = `min(max_delay, base_delay * 2**(i-1))`。

### 2.2 Tier 1 — LLM 邊界（`make_plan` / `make_draft`）

把 Gemini 呼叫包進 `call_with_retry`：

```python
try:
    steps = call_with_retry(lambda: llm_plan(query, client))
except Exception:
    steps = []
return steps or fallback_plan(query)
```

- 暫時性抖動 → 重試最多 3 次 → **撐過就保住 LLM 答案**。
- 持續失敗 / 永久性錯誤 → 既有 `except → fallback` 優雅降級。
- 空輸出仍非例外 → 照舊 `or fallback`。
- **這是今天就會觸發的層。**

### 2.3 Tier 2 — 節點層保險絲（`@traced`）

```python
def traced(node_name, *, retries=0, retry_on=is_transient): ...
```

- opt-in，預設 `retries=0` = **今天完全一樣的行為**。
- `retries>0` 時，在既有 try/except **內** 用 `call_with_retry(attempts=retries+1)`
  包住節點呼叫；用盡後例外照樣變 error trace + `halt=True`
  →（**FR-009 不變**：不讓半成品狀態外洩給下游）。
- 啟用 `retries=2` 的節點：**retriever**、**calculator**（R4 接真實
  向量檢索 / BigQuery I/O 後才會有的暫時性失敗）。
- planner / writer 維持 `retries=0`（已被 Tier 1 覆蓋，避免雙重重試）；
  compliance 純確定性 → `retries=0`。

> 今天 retriever / calculator 不會暫時性失敗，所以 Tier 2 對現有行為**零影響**；
> 它是把保險絲先接好、機制由合成 flaky 節點測試驗證。

### 2.4 為何不用 LangGraph 原生 `RetryPolicy`

`add_node(retry=RetryPolicy(...))` 靠節點 fn **丟出** 例外才重試 —— 但 `@traced`
依設計（FR-009）會**吞掉**例外，RetryPolicy 永遠收不到。要用它就得讓 `traced`
重新拋出，等於把半成品狀態洩給下游、違反 FR-009。自建 primitive 與既有
例外邊界乾淨組合，故不採原生 RetryPolicy。

## 3. 測試（TDD，紅→綠，全程 token=0）

| 測試檔 | 案例 |
|---|---|
| `test_retry.py` | 首次成功（1 次呼叫、不 sleep）；N 次後恢復（驗呼叫數 + 注入 sleep recorder 的 backoff 序列）；用盡 → re-raise 最後例外；永久性（`retry_on` False）→ 立即 raise、不 sleep；`is_transient` 對 429/503/timeout=True、400/`ValueError`=False |
| `test_planner_agent.py`（增） | 暫時性後恢復 → 回 LLM 結果（`generate` 呼叫 3 次）；持續暫時性 → 3 次後 fallback；永久性 → 立即 fallback（1 次） |
| `test_writer_agent.py`（增） | 同上形狀 |
| `test_traced_retry.py` | 合成 flaky 節點：重試後恢復（單一 OK trace）；持續失敗 → 單一 error trace + `halt`（證 FR-009 不變、無多餘 trace） |
| `conftest.py`（增） | `FakeLLM` 加 `fail_times` / `error`；加 `no_retry_sleep` fixture + `_ApiError(code)` helper |

## 4. 影響檔案

- **新增**：`src/polaris/retry.py`、`tests/test_retry.py`、`tests/test_traced_retry.py`
- **修改**：`src/polaris/graph/nodes/trace.py`、`src/polaris/graph/nodes/stubs.py`、
  `src/polaris/graph/nodes/planner_agent.py`、`src/polaris/graph/nodes/writer_agent.py`、
  `tests/conftest.py`、`tests/test_planner_agent.py`、`tests/test_writer_agent.py`
- **不動**：`src/polaris/graph/workflow.py`、`src/polaris/graph/state.py`

## 5. 非目標（YAGNI）

- 不接 LLMLingua（W2 D8）。
- 不為 `GeminiClient.embed` 包 retry（R4 接檢索時再依同一 primitive 補）。
- 不引入 logger / metrics（observability 待後續週次；retry 行為以 trace + 測試驗證）。
- 不改 `state.py`（不新增 `attempts` 欄位；如 G2 需要可後補，向後相容）。
