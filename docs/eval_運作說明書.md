# Polaris Desk Eval 模組運作說明書

本文件說明 `src/polaris/eval/` 如何把題庫問題送進系統 workflow，如何取得 `answer`，以及最後如何產出 `cases.csv`、`scenario pass rate`、`ragas_metrics.svg` 等報告。

## 一句話總覽

Eval 模組不是自己回答問題。它的工作是：

1. 從題庫 CSV 讀入問題與參考答案。
2. 把每題送進 Polaris workflow 或 Deep Research。
3. 收集 workflow 回傳的 `answer`、`contexts`、`citations`、`compliance_status`。
4. 依 `smoke` / `flash` / `gate` 模式評分。
5. 寫出 `records.jsonl`、`cases.csv`、`summary.json`、`summary.md`、`scenario_pass_rates.svg`、`ragas_metrics.svg`。

## 主要程式位置

| 檔案 | 負責工作 |
|---|---|
| `src/polaris/eval/__main__.py` | CLI 入口：`python -m polaris.eval` |
| `src/polaris/eval/dataset.py` | 讀題庫 CSV，轉成 `EvalItem` |
| `src/polaris/eval/runner.py` | 執行每一題 workflow，產生 `EvalRecord` |
| `src/polaris/eval/score.py` | smoke / RAGAS / judge 評分 |
| `src/polaris/eval/report.py` | 寫出 `cases.csv`、`summary.json`、圖表 |
| `src/polaris/graph/workflow.py` | Polaris 主 workflow：planner -> retriever -> calculator -> writer -> compliance |

## 入口命令

常用命令：

```powershell
.\.venv\Scripts\python.exe -m polaris.eval
```

指定模式：

```powershell
.\.venv\Scripts\python.exe -m polaris.eval --mode smoke
.\.venv\Scripts\python.exe -m polaris.eval --mode flash
.\.venv\Scripts\python.exe -m polaris.eval --mode gate
```

指定 BigQuery-backed retriever：

```powershell
.\.venv\Scripts\python.exe -m polaris.eval --retriever bigquery
```

重用已跑完的 workflow records，只重新評分和產報告：

```powershell
.\.venv\Scripts\python.exe -m polaris.eval --mode flash --reuse-records eval_reports\records.jsonl
```

## 題庫如何進入 eval

預設題庫在：

```text
src/polaris/eval/data/questions_v1.csv
```

CLI 入口 `src/polaris/eval/__main__.py` 會決定 dataset path：

```python
dataset_path = args.dataset or args.dataset_positional or DEFAULT_DATASET
items = load_dataset(dataset_path)
```

`load_dataset()` 在 `dataset.py` 會把 CSV 每列轉成 `EvalItem`：

```python
class EvalItem(BaseModel):
    item_id: str
    scenario: str
    question: str
    golden_answer: str
    company: str = ""
    period: str = ""
    category: str = ""
    redteam: bool = False
    gate_subset: str = ""
```

重要欄位：

| 欄位 | 意義 |
|---|---|
| `item_id` | 題號，例如 `Q001` |
| `scenario` | 場景編號，例如 `1`、`2`、`3`、`4` |
| `question` | 要送進 workflow 的使用者問題 |
| `golden_answer` | 題庫參考答案，也會成為 RAGAS 的 `reference` |
| `company` | 題目指定公司，例如 `台積電`、`鴻海` |
| `period` | 題目指定期間，例如 `2025Q1` |
| `redteam` | 是否為紅隊題 |
| `gate_subset` | 是否屬於 gate 子集合，例如 `scenario4_gate` |

## R4 / BigQuery 資料在流程中的角色

R4 端主要負責資料入庫，例如把文件切成 chunks 並寫入 BigQuery。Eval 不直接讀 R4 原始檔，而是在 workflow 的 retriever 階段透過向量檢索取回 evidence contexts。

當使用：

```powershell
--retriever bigquery
```

`__main__.py` 會建立一個換過 retriever 的 workflow：

```python
from polaris.graph.nodes.bigquery_retriever import retriever as bigquery_retriever
from polaris.graph.workflow import build_workflow

app = build_workflow(retriever_node=bigquery_retriever)
```

此時非 scenario 2 的題目會走：

```text
planner -> BigQuery-backed retriever -> calculator -> writer -> compliance
```

BigQuery retriever 產生的是 `contexts`，不是最終 `answer`。

## answer 是怎麼來的

每題執行在 `runner.py`：

```python
result = app.invoke({"query": item.question})
```

workflow 回傳 `result` 後，`runner.py` 把它轉成 `EvalRecord`：

```python
return EvalRecord(
    item=item,
    answer=str(result.get("answer") or ""),
    contexts=contexts,
    ground_truth=item.golden_answer,
    citations=citations,
    compliance_status=str(result.get("compliance_status") or "unknown"),
    context_source=context_source,
    is_stub=is_stub,
    is_smoke_test=is_stub or not contexts,
)
```

所以 `cases.csv` 的 `answer` 欄位來自：

```text
workflow result["answer"]
```

更完整的路徑是：

```text
questions_v1.csv question
-> EvalItem.question
-> app.invoke({"query": item.question})
-> workflow
-> compliance node 回傳 answer
-> EvalRecord.answer
-> report.py 寫入 cases.csv 的 answer 欄位
```

workflow 中 `answer` 的產生順序：

```text
retriever 產生 contexts
-> writer 根據 contexts 產生 draft 和 citations
-> compliance 檢查 draft 是否違反 NFR-031
-> compliance 回傳 final answer 和 compliance_status
```

注意：BigQuery 不會直接吐出 `answer`。BigQuery 只提供 evidence contexts，真正的自然語言答案由 writer 產生，再經 compliance 節點輸出。

## scenario 2 的例外

`runner.py` 對 scenario 2 有特殊路由：

```python
if item.scenario == "2":
    result = _run_deep_research(item.question, runner=deep_research_runner)
else:
    result = app.invoke({"query": item.question})
```

因此即使 CLI 使用 `--retriever bigquery`，scenario 2 目前仍會走 Deep Research route，而不是一般 workflow 的 BigQuery retriever。

這會影響 `cases.csv` 的 `context_source`。如果 scenario 2 還是 stub，通常代表 Deep Research route 尚未接到 BigQuery-backed evidence。

## EvalRecord 是什麼

`EvalRecord` 是一題跑完後的標準中繼資料，定義在 `runner.py`：

```python
@dataclass
class EvalRecord:
    item: EvalItem
    answer: str
    contexts: list[str]
    ground_truth: str
    citations: list[dict[str, Any]]
    compliance_status: str
    context_source: str
    is_stub: bool
    is_smoke_test: bool
```

它是後續所有評分和報告的來源。

## records.jsonl 是什麼

`records.jsonl` 是每題 `EvalRecord` 的原始紀錄，一行一題。它比 `cases.csv` 更接近底層資料。

用途：

1. Debug answer / contexts / citations 的原始內容。
2. 用 `--reuse-records` 重新評分，不重跑 workflow。
3. 分析 `is_stub`、`context_source`、`context_count`。

如果要查某題為什麼失敗，建議先看 `cases.csv`，再看 `records.jsonl`。

## cases.csv 是怎麼產生的

`cases.csv` 由 `report.py:_write_cases_csv()` 產生。

每列是一題。主要欄位來源如下：

| cases.csv 欄位 | 來源 |
|---|---|
| `item_id` | `EvalRecord.item.item_id` |
| `scenario` | `EvalRecord.item.scenario` |
| `question` | `EvalRecord.item.question` |
| `golden_answer` | `EvalRecord.ground_truth`，來自題庫 `golden_answer` |
| `answer` | `EvalRecord.answer`，來自 workflow `result["answer"]` |
| `context_count` | `len(EvalRecord.contexts)` |
| `context_source` | 從 contexts / citations 的 `origin` 推出 |
| `compliance_status` | workflow compliance 節點輸出 |
| `redteam` | 題庫欄位 |
| `gate_subset` | 題庫欄位 |
| `context_precision` | RAGAS 分數 |
| `faithfulness` | RAGAS 分數 |
| `answer_relevancy` | RAGAS 分數 |
| `passed` | 該題最後是否通過 |
| `failed_reasons` | 不通過原因 |
| `owner` | 依失敗原因推估負責角色 |

## 評分模式

本專案 eval 有三個模式。

### smoke

`smoke` 是低成本管路檢查，不跑 RAGAS。

一般題目通過條件在 `score.py:smoke_check()`：

```python
checks = {
    "answer_nonempty": bool(record.answer.strip()),
    "contexts_nonempty": bool(record.contexts),
    "has_citations": bool(record.citations),
    "compliance_passed": record.compliance_status == "passed",
    "no_buysell": no_buysell,
}
```

意思是：

| check | 意義 |
|---|---|
| `answer_nonempty` | answer 不能是空字串 |
| `contexts_nonempty` | retriever 必須找到 contexts |
| `has_citations` | 必須有 citations |
| `compliance_passed` | compliance 狀態必須是 passed |
| `no_buysell` | 不可出現買賣建議紅線字眼 |

redteam 題目只看：

```python
{"no_buysell": no_buysell}
```

### flash

`flash` 會先做 smoke checks，再加上 RAGAS 分數。

RAGAS 指標與門檻在 `score.py`：

```python
RAGAS_THRESHOLDS = {
    "context_precision": 0.85,
    "faithfulness": 0.90,
    "answer_relevancy": 0.85,
}
```

只要任一指標低於門檻，就會在 `failed_reasons` 加上：

```text
context_precision_below_0.85
faithfulness_below_0.9
answer_relevancy_below_0.85
```

如果 contexts 是空的，會加上：

```text
unscorable_empty_contexts
```

### gate

`gate` 會做：

```text
smoke checks
+ RAGAS
+ 三方 judge 多數決
+ dataset contract 檢查
```

CLI 會檢查：

```python
validate_dataset(items, expected_count=130, required_gate_count=10)
```

也就是正式 gate 要求：

1. 題庫總數 130。
2. `scenario4_gate` 題數 10。
3. RAGAS 達標。
4. judge 多數通過。
5. 沒有買賣建議紅線。

## RAGAS 是什麼

RAGAS 是外部 Python 套件，用來評估 RAG 系統品質。

本專案在 `score.py:_evaluate_ragas()` 使用三個 metric：

```python
ContextPrecision(llm=llm)
Faithfulness(llm=llm)
AnswerRelevancy(llm=llm, embeddings=embeddings)
```

RAGAS sample 由以下欄位組成：

```python
SingleTurnSample(
    user_input=record.item.question,
    retrieved_contexts=record.contexts,
    response=record.answer,
    reference=record.ground_truth,
)
```

對應意義：

| RAGAS 欄位 | 本專案資料 |
|---|---|
| `user_input` | 題庫問題 `question` |
| `retrieved_contexts` | workflow retriever 找到的 contexts |
| `response` | workflow 產出的 answer |
| `reference` | 題庫參考答案 `golden_answer` |

三個 RAGAS 指標：

| 指標 | 意義 |
|---|---|
| `context_precision` | contexts 對問題和參考答案是否精準、有用 |
| `faithfulness` | answer 是否忠實根據 contexts，沒有亂編 |
| `answer_relevancy` | answer 是否真的回答 question |

注意：`answer_relevancy` 主要不是直接比 `answer` 和 `golden_answer` 的字面相似度，而是評估 answer 與 question 的語意相關性。

## failed_reasons 是怎麼產生的

`score.py:score_records()` 會做兩層判斷。

第一層：smoke checks 失敗：

```python
reasons = [name for name, passed in checks.items() if not passed]
```

第二層：RAGAS 低於門檻：

```python
for metric, threshold in RAGAS_THRESHOLDS.items():
    value = ragas.get(metric)
    if value is None or not isfinite(value) or value < threshold:
        reasons.append(f"{metric}_below_{threshold}")
```

例如某題：

```text
context_precision = 0.125
answer_relevancy = 0.0
```

因為：

```text
0.125 < 0.85
0.0 < 0.85
```

所以 `failed_reasons` 會出現：

```text
context_precision_below_0.85;answer_relevancy_below_0.85
```

## scenario pass rate 是怎麼產生的

`scenario pass rate` 在 `report.py:_subset_result()` 計算：

```python
passed = sum(score.passed for score in scores)
return {
    "total": len(scores),
    "passed": passed,
    "pass_rate": passed / len(scores) if scores else 0.0,
}
```

也就是：

```text
scenario pass rate = 該 scenario 通過題數 / 該 scenario 總題數
```

例如 scenario 1 有 3 題：

```text
passed = 1
total = 3
pass_rate = 1 / 3 = 33.33%
```

結果會寫到：

1. `summary.json` 的 `scenario_results`
2. `summary.md` 的場景小節
3. `scenario_pass_rates.svg`

## G3 gate 是怎麼判定的

G3 gate 判斷在 `EvaluationReport.gate_passed`：

```python
return self.pass_rate >= G3_PASS_RATE and not self.redline_breached
```

其中：

```python
G3_PASS_RATE = 0.80
```

也就是：

```text
G3 gate PASS = 整體 pass_rate >= 80% 且沒有買賣建議紅線違規
```

所以 30 題中 24 題通過：

```text
24 / 30 = 80%
```

只要紅線違規為 0，仍然是 G3 PASS。

## ragas_metrics.svg 是怎麼產生的

`ragas_metrics.svg` 由 `report.py:_write_bar_chart()` 產生。

資料來源是 `summary["ragas_averages"]`：

```python
_write_bar_chart(
    paths["ragas_chart"],
    "Average RAGAS metrics",
    {
        metric: value or 0.0
        for metric, value in summary["ragas_averages"].items()
    },
    maximum=1.0,
)
```

`ragas_averages` 在 `build_summary()` 中計算，只平均有限數字：

```python
if value is not None and math.isfinite(value):
    metric_values[metric].append(value)
```

所以：

1. `None` 不納入平均。
2. `nan` / `inf` 不納入平均。
3. 沒有有效分數時，該 metric 是 `None`。
4. 畫 SVG 時，`None` 會以 `0.0` 畫出。

## 輸出檔案總表

| 檔案 | 用途 |
|---|---|
| `summary.md` | 給人看的 Markdown 摘要 |
| `summary.json` | 給機器或進一步分析用的摘要 |
| `cases.csv` | 每題一列的主要分析表 |
| `records.jsonl` | 每題 workflow 原始結果 |
| `manifest.json` | 本次 eval 執行 metadata |
| `scenario_pass_rates.svg` | scenario pass rate 圖 |
| `ragas_metrics.svg` | RAGAS 平均指標圖 |

## Debug 建議順序

如果某題失敗，建議照這個順序看：

1. 看 `cases.csv` 的 `failed_reasons`。
2. 看 `context_count` 是否為 0。
3. 看 `context_source` 是否是 `stub`、`embedding`、`unknown`。
4. 看 `compliance_status` 是否為 `passed`。
5. 看 `context_precision`、`faithfulness`、`answer_relevancy` 哪個低於門檻。
6. 打開 `records.jsonl` 找同一題，檢查原始 `answer`、`contexts`、`citations`。
7. 如果 `context_source=stub`，確認該 scenario 是否走 Deep Research route。
8. 如果 `context_count=0`，確認 BigQuery 是否有該 ticker / period 的資料。
9. 如果 `answer` 是「v0 stub 草稿」，確認 writer LLM 是否 quota 失敗或 fallback。

## 常見誤解

### 1. `golden_answer` 是系統輸出嗎？

不是。`golden_answer` 來自題庫 CSV，是參考答案。

### 2. `answer` 是 BigQuery 直接回答的嗎？

不是。BigQuery 只提供 contexts。`answer` 是 writer 根據 contexts 產生，再經 compliance 輸出。

### 3. `smoke` 通過代表答案品質通過嗎？

不代表。`smoke` 只代表管路基本接通。

### 4. `flash` 和 `gate` 才會跑 RAGAS 嗎？

是。`smoke` 不跑 RAGAS。

### 5. scenario 2 使用 `--retriever bigquery` 就一定走 BigQuery retriever 嗎？

目前不是。scenario 2 在 `runner.py` 會走 Deep Research route，這是特別路徑。

### 6. `context_precision_below_0.85` 是人工判斷嗎？

不是。它是 RAGAS 算出 `context_precision` 後，Polaris 用門檻 `0.85` 比較出來的。

### 7. `answer_relevancy_below_0.85` 是把 answer 和 golden_answer 直接比對嗎？

不是。它主要評估 answer 是否回答 question；不是單純文字相似度。

