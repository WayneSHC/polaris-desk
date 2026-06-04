# R2 W2 D8 — LLMLingua POC（prompt 壓縮 token 省幅量測）設計

**日期**：2026-06-03 ｜ **角色**：R2 AI 架構師（施惠棋 / WayneSHC）
**對應**：spec SC-006「LLMLingua 量到 **token 省 ≥ 50%**」、R2 spec §3 W2 D8
**前置**：W1 D1–D4（5 節點骨架）、W2 D6（Temporal Anchoring）、W2 D7（retry primitive）

---

## 1. 目標與範圍

交付一套 **prompt 壓縮 token 省幅「量測 harness」**，建立在可抽換的 `Compressor` 抽象層之上。

- **In scope**：壓縮抽象層（介面 + 確定性基線 + LLMLingua 選用 backend）、token 計數抽象層、量測 harness、POC runner、設計文件。
- **Out of scope（本任務刻意不做）**：把壓縮**接進 live graph**（retriever→writer）。理由見 §4。

### 為什麼是「量測 only」、不接進 pipeline
spec 對 D8 的驗收是「**量** token 省幅 ≥ 50%」，不是「壓縮已上線」。在尚未量測壓縮對**答案品質 / 引用接地（FR-004）**的影響前就改動 retriever→writer，會冒接地退化的風險。POC 的責任是量測；live 整合是日後另一個獨立、另行設閘的步驟（YAGNI）。

---

## 2. 為什麼 LLMLingua 走「smart backend + 確定性 fallback」

真正的 `llmlingua` 套件會拉進 `torch` + `transformers` + 模型權重（~2GB、需下載），與本專案兩個既有約束直接衝突：
- **CI token-free / 無重依賴**：CI 不得依賴 GPU/大模型下載。
- **輕量 Drive 同步開發環境**：~2GB 套件 + 權重不適合同步資料夾。

因此採用與 Gemini 節點**完全相同**的 smart-node 模式（`active_llm()`）：

| 層 | 預設（CI / 無 extra） | 真實 backend（裝了 `[llmlingua]` extra） |
|---|---|---|
| 壓縮 | `DeterministicCompressor`（純 Python、token-free、誠實量到多少報多少） | LLMLingua backend（hit ≥ 50% 目標） |

`active_compressor()` 在執行期挑選：裝了且啟用 → LLMLingua；否則 → 確定性。**真實 backend 到位時零結構改動**。

### ≥ 50% 驗收如何達成（誠實，不 game 假語料）
- CI **不**硬斷言 ≥ 50%——確定性基線在密集中文財經文字上誠實達不到 50%，硬調到 50% 等於對冗長的 stub 假語料（含「（v0 stub）」前綴）game 指標。
- ≥ 50% 由**本機跑真 LLMLingua backend**對代表性語料產生，數字寫進本設計文件 §6 與 POC runner 輸出留底。
- CI 測試只驗證 harness 數學正確 + 壓縮確實減少 token（> 0%）+ 抽象層可抽換。

---

## 3. 架構：新套件 `src/polaris/compression/`

刻意切成小而界線清楚的單元（與 `graph/temporal.py`、`retry.py` 同風格）。

| 模組 | 單一職責 |
|---|---|
| `tokens.py` | `count_tokens(text) -> int`。優先 backend：**tiktoken `cl100k_base`**（離線、確定性）；缺套件時退確定性 regex 估計（CJK 逐字 + latin 詞/標點）。永不 raise，空字串→0。 |
| `compressors.py` | `Compressor` Protocol（`compress(text)->str`）；`DeterministicCompressor`（常駐、token-free：壓白、去 boilerplate 前綴、去重複句）；`make_llmlingua_compressor()`（只在裝了 `llmlingua` 時 import）；`active_compressor()`（鏡像 `active_llm()`）。 |
| `measure.py` | `CompressionResult` dataclass（`original_tokens / compressed_tokens / saved_tokens / saved_pct / compressor_name`）；`measure_contexts(contexts, *, compressor, count)`——以**與 `writer_agent._format_contexts` 相同**的邏輯攤平 contexts，量到的就是真實 prompt payload；`format_report()`。 |
| `__main__.py` | POC runner：`python -m polaris.compression` → 對 D6 stub 語料 + 代表性較長中文財經片段跑 `measure_contexts`，印出報告。 |

### 資料流（量測）
```
contexts → _format_contexts → original_str → count_tokens ⇒ original_tokens
original_str → compressor.compress → compressed_str → count_tokens ⇒ compressed_tokens
saved_pct = (original_tokens − compressed_tokens) / original_tokens × 100
```
與 graph 零耦合 → `stubs.py` / `workflow.py` byte 不動 → `test_node_swap` + 5 節點 trace 契約不變（FR-007 / SC-005）。

---

## 4. 錯誤處理 / 邊界

- `count_tokens`：空 / None → 0，永不 raise。
- `compress`：空輸入 → 空輸出，永不 raise。
- `measure_contexts`：空 contexts → `saved_pct=0.0`（不除零）。
- LLMLingua import 失敗 → 靜默退 `DeterministicCompressor`（鏡像 `active_llm()` 的 None 路徑）。

---

## 5. 依賴

- 明確在 `[project.dependencies]` 宣告 **`tiktoken`**（目前僅為 transitive），讓 token 計數的真實 backend 是「刻意」而非「偶然」；但程式碼缺它仍能退 regex 估計。
- 新增 optional extra **`[llmlingua]`**（`torch` / `transformers` / `llmlingua`）；預設 / CI 安裝不含 → CI 維持輕量。

---

## 6. 量測結果留底（本機真 LLMLingua-2 已跑完，2026-06-04 回填）

**環境**：`~/code/polaris-desk`、`[llmlingua]` extra（llmlingua 0.2.2 / torch 2.12 / transformers 5.10），
LLMLingua-2 模型 `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank`（多語含中文、`device_map=cpu`）。
token 計數＝tiktoken `cl100k_base`（本環境已裝；**同一 counter 同時量原文與壓縮文**，故 rate 與絕對 tokenizer 不影響「相對省幅」結論）。

**確定性基線**（`python -m polaris.compression`，常駐 token-free）：

| 語料 | original | compressed | saved_pct |
|---|---|---|---|
| D6 stub 語料 | 240 | 220 | 8.33% |
| 代表性較長片段 | 276 | 256 | 7.25% |

**LLMLingua-2 真 backend**（`POLARIS_USE_LLMLINGUA=1 [POLARIS_LLMLINGUA_RATE=…] python -m polaris.compression`），rate 掃描：

| 語料 | rate=0.5（預設）| rate=0.4 | **rate=0.33** | rate=0.25 | rate=0.2 |
|---|---|---|---|---|---|
| D6 stub 語料 | 32.08% | 45.42% | **55.83%** | 68.33% | 75.0% |
| 代表性較長片段 | 34.42% | 46.74% | **55.43%** | 64.49% | 73.19% |

**✅ SC-006 達成**：LLMLingua-2 在 **rate≈0.33**（保留 ~1/3 詞）對兩個語料皆 **省 ≥ 50%**
（55.83% / 55.43%，以**獨立的 tiktoken cl100k** 量測，非採 llmlingua 自報 ratio）。
可重現：`POLARIS_USE_LLMLINGUA=1 POLARIS_LLMLINGUA_RATE=0.33 python -m polaris.compression`。

**解讀與取捨**：
- 預設保守 rate=0.5 在中文短財經片段、以 tiktoken 量只 ~33%——因 LLMLingua 的 rate 是「保留**詞**比例」，
  被丟的多是低資訊虛詞 / 重複，保留的數字 / 專名在 tiktoken 下每詞 token 較多，故 tiktoken 省幅 < rate。
- 達 ≥50% 需更積極（rate≈0.33）；但**更積極壓縮＝更可能傷及引用接地**（數字 / `[source_id]` 標記）——
  這正是 §4「**量測 only、未接 live graph**」的理由：live 整合須先量壓縮對答案品質 / FR-004 接地的影響、另行設閘。
- 確定性基線只靠去 boilerplate / 壓白 / 去重複行，誠實 ~7–8%，遠不及 50%——≥50% 必須靠 LLMLingua 小模型的 perplexity 評分。
- 註：舊版 §6 基線（145/181）係 tiktoken 未安裝時的 regex 估計值；本次統一改用 tiktoken cl100k，全表同一 counter。

---

## 7. 測試（TDD，red-green-refactor）

- **tokens**：空→0；非空>0；越長 token 嚴格越多（單調）；CJK 計數；tiktoken 缺席 fallback（monkeypatch `find_spec`→None）；確定性。
- **compressors**：確定性壓縮器壓後 token ≤ 原文；**保留 `[source_id]` 標記**（接地不破）；確定性；空→空不 raise；`active_compressor()` 在 llmlingua 缺席時回 `DeterministicCompressor`。
- **measure**：`saved_pct` 數學 + 四捨五入；冗長語料 → `saved_pct>0`；空 contexts → `0.0` 不除零；`format_report` 含關鍵數字；measure 使用 writer 的攤平邏輯。

---

## 8. Constitution 遵循

- **VI / III**：N/A——壓縮在 LLM 之前、token-free、無金鑰、無買賣內容。
- 不觸碰 NFR-031 相關輸出路徑。

---

## 9. 交付物

程式 + 測試（TDD）· `python -m polaris.compression` runner · 本設計文件 · R2 spec D8 → `[x]`（repo + Drive mirror）· 專案記憶更新 · PR + admin-merge（沿用 PR #11/#12/#14 模式）。
