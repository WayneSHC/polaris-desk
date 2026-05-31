# Feature Specification: LangGraph 5-Node Skeleton (Stub Mode)

**Feature Branch**: `r2/001-langgraph-skeleton`

**Created**: 2026-05-31

**Status**: Draft

**Input**: User description: "R2 W1 D1：搭一個端到端跑得起來的 5 節點 LangGraph 骨架（Planner → Retriever → Calculator → Writer → Compliance），每節點先回固定假資料；一個自然語言問題進來、能拿到一段帶引用的答案出去，且任何疑似買賣建議的草稿在送出前被 Compliance 攔截。此骨架是後續 R3 把真 agent 一個一個換進去、R5 寫 e2e 驗收的地基。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — 隊友可以對骨架送問題、拿到帶引用的假答案 (Priority: P1)

R3（Agent 工程師）或 R5（Eval）把一個自然語言問題（例：「台積電 2025 Q1 營收 YoY 是多少？」）送進工作流，5 個節點依序執行，最後回傳一段帶 ≥1 條引用的草稿答案。

**Why this priority**: 沒有這條走通的端到端骨架，R3 沒有掛真 agent 的插座、R5 沒有 e2e 驗收的對象、R7 沒有可串的後端契約。這是 W1 G1 與整個 4 週 sprint 的解鎖前提。

**Independent Test**: 跑一個 e2e 測試／CLI 指令，輸入一個問題字串；驗收：(a) 5 個節點各執行一次且有 trace 紀錄、(b) 回傳結構含 `answer` 與 `citations`、(c) 即使所有節點皆 stub，整個流程不需人工介入即可結束。

**Acceptance Scenarios**:

1. **Given** 骨架已部署且所有節點處於 stub mode，**When** 輸入「台積電 2025 Q1 營收 YoY」這類問題，**Then** 系統在 10 秒內回傳一段固定的假答案，內含至少 1 條 stub 引用（含來源 ID 與片段文字）。
2. **Given** 骨架可執行，**When** 開發者跑 e2e 測試，**Then** 測試輸出包含 5 個節點的執行 trace，且每個節點都顯示 input keys 與 output keys。

---

### User Story 2 — Compliance 節點攔下任何疑似買賣建議的草稿 (Priority: P1)

Writer 節點產出的草稿在送出前必過 Compliance 節點檢查。若草稿含「建議買進／賣出／加碼／減碼／看多／看空」等明顯買賣指令，Compliance 必須改寫結果或退件，最終輸出不得含買賣建議。

**Why this priority**: NFR-031（投顧執照風險）是專題憲法硬約束，任何 demo / 對外輸出含買賣建議即 No-Go。骨架沒有這層攔截，等於整套工作流帶法律風險上線。

**Independent Test**: 餵 Writer 一段含「建議買進」字眼的固定草稿，跑完 Compliance 節點後，驗收最終 `answer` 欄位中**不含**任何買賣建議關鍵字，且 `compliance_status` 標記為 `blocked` 或 `rewritten`。

**Acceptance Scenarios**:

1. **Given** Writer stub 回傳「建議買進台積電」這段固定文字，**When** Compliance 節點執行，**Then** 最終 `answer` 不含「建議買進／賣出」字串，且狀態欄標記攔截行為。
2. **Given** Writer stub 回傳合規內容（純事實描述 + 引用），**When** Compliance 節點執行，**Then** 草稿原封不動進入最終輸出，狀態欄標記 `passed`。

---

### User Story 3 — 任一節點可獨立替換為真實實作而不動工作流定義 (Priority: P2)

R3 在 W1 D2 之後會把 Planner、Calculator、Writer 等節點一個一個換成真 agent；R4 換 Retriever；R6 提供 Compliance 規則。骨架必須讓「換掉一顆節點」這件事不需要動到工作流的串接定義。

**Why this priority**: 這是骨架的存在意義之一，但 W1 D1 只要骨架能跑就先有價值；節點替換是 D2 之後的事，因此降為 P2。

**Independent Test**: 把任一節點 stub 換成另一個會回不同假答案的版本，跑 e2e；驗收：工作流串接檔案（節點順序、邊定義）**未被修改**，且最終輸出反映新節點行為。

**Acceptance Scenarios**:

1. **Given** Planner 節點 stub v1（回固定步驟），**When** 替換為 Planner stub v2（回不同步驟），**Then** 工作流定義檔無 diff，且最終輸出的 trace 顯示 v2 的步驟內容。

---

### Edge Cases

- **空問題輸入**：使用者送空字串或只有空白的問題進來時，系統必須在第一個節點即拒絕並回固定錯誤訊息，不得讓空狀態傳到後續節點。
- **節點 stub 拋例外**：W1 D1 不做 retry；任一節點拋例外時，系統必須將例外訊息與發生節點名稱寫入 trace 並中止，**不得**讓後續節點吃到 undefined state。
- **Compliance 既不通過也不改寫**：若 Compliance 判定無法安全產出（例如 stub 回 `unknown`），系統必須回固定的安全訊息（如「本系統不提供買賣建議」），而非把原草稿露出。
- **重複跑同一問題**：同一問題重跑必須得到相同結果（stub 是確定性的），方便 R5 寫 snapshot 測試。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系統 MUST 接受一個自然語言問題字串作為唯一輸入（W1 不接 ticker / 期間結構化欄位，留給 W2 Temporal Anchoring）。
- **FR-002**: 系統 MUST 以固定順序執行 5 個節點：Planner → Retriever → Calculator → Writer → Compliance。
- **FR-003**: 每個節點 MUST 接收前一節點的輸出狀態、回傳擴充後的狀態給下一節點；節點間的狀態結構 MUST 是型別化的（每個欄位用途定義清楚）。
- **FR-004**: 系統 MUST 在最終輸出回傳兩個核心欄位：`answer`（字串）與 `citations`（≥0 條引用清單）；W1 stub 模式下每筆引用至少含「來源 ID」與「片段文字」兩欄。
- **FR-005**: Compliance 節點 MUST 對 Writer 產出的草稿做關鍵字檢查，含買賣建議字眼（W1 至少涵蓋：建議買進、建議賣出、加碼、減碼、看多、看空）時 MUST 改寫或退件，最終輸出 MUST 不含這些字眼。
- **FR-006**: 系統 MUST 為每次執行產出可讀的 trace，包含每個節點的：節點名稱、執行時間、輸入欄位鍵清單、輸出欄位鍵清單。
- **FR-007**: 系統的工作流結構（節點順序與邊）MUST 與節點實作分離，使單一節點被替換時，工作流定義檔案無需修改。
- **FR-008**: 系統 MUST 在輸入為空字串或全空白時，於 Planner 節點即返回固定錯誤狀態，不讓空狀態流到下游節點。
- **FR-009**: 系統 MUST 在任一節點拋例外時，將例外訊息與發生節點名稱寫入 trace 並安全中止，不得讓下游節點吃到 undefined 狀態。
- **FR-010**: 同一問題重複輸入 MUST 在 stub 模式下產生相同結果（節點 stub 為確定性，無隨機）。

### Key Entities

- **Question**：使用者送進來的請求；W1 包含一個欄位：`text`（原始問題字串）。後續週次會擴充為含 ticker / 期間 / 場景類型。
- **ResearchState**：5 個節點共用的狀態物件；至少包含 `question`、`plan`（Planner 產出）、`retrievals`（Retriever 產出）、`calculations`（Calculator 產出）、`draft`（Writer 產出）、`citations`、`compliance_status`、`trace`。
- **Citation**：引用單筆紀錄；至少含 `source_id`（來源識別）、`snippet`（被引用的文字片段）、`origin`（W1 固定為 `stub`，後續週次擴為 `bm25`、`embedding`、`colpali`、`rerank`、`news`）。
- **NodeTrace**：單一節點的執行紀錄；至少含 `node_name`、`status`（ok／error）、`input_keys`、`output_keys`、`error_message`（如有）。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 端到端跑一個範例問題、在 stub 模式下，從輸入到 `answer` + `citations` 回傳的全程**人工介入次數 = 0**。
- **SC-002**: 一次 e2e 執行的 trace 必須完整列出 5 個節點且**每個節點都有 status 標記**（100% 覆蓋）；無節點被略過、無節點 status 為 unknown。
- **SC-003**: Compliance 節點對 6 條已知買賣建議關鍵字測試輸入的攔截率 **= 100%**；最終 `answer` 中出現買賣建議字眼的測試案例數 **= 0**。
- **SC-004**: 從一個範例問題輸入到 `answer` 返回的總耗時，在 stub 模式且本機開發環境下 **< 10 秒**（不含開發伺服器啟動時間）。
- **SC-005**: 將任一節點 stub 換為等效但回不同假答案的版本，**工作流定義檔案的 diff 必為 0 行**；最終輸出能反映替換後節點的行為。
- **SC-006**: 對同一範例問題連續執行 3 次，3 次的 `answer` 與 `citations` **完全相同**（確定性驗證，便於 R5 寫 snapshot 測試）。
- **SC-007**: 空字串／全空白輸入時，回傳一個固定錯誤訊息，且 trace 顯示「只有 Planner 節點被執行」（**下游 4 節點 status 不存在**）。

## Assumptions

- **Stub 即固定假資料**：W1 D1 不呼叫任何 LLM，所有節點回的內容是寫死的 fixture；這讓 W1 D1 的 token cost = $0，且確定性可重現。
- **Compliance 關鍵字清單 W1 用最小集**：6 個明顯關鍵字（建議買進／賣出、加碼、減碼、看多、看空）夠擋骨架階段的紅線；完整規則由 R6 在 W3 補。
- **單問題、同步模式**：W1 D1 一次處理一個問題、同步等到結果回來；async／streaming／批次留到後續週次。
- **R2 W1 D1 的成功 = 端到端跑通**：節點實作的「智力」不在 D1 範圍內；D2 之後 R3 與 R6 才會把真 agent 推進來。
- **既有 starter repo 已就緒**：本 spec 假設 starter repo 中 `src/polaris/graph/workflow.py` 既有的 5 節點空骨架可直接擴充，不需重起一個工作流框架。
- **與憲法相容**：本 feature 落實 Principle I（NFR-031）與 Principle II（引用接地）的最小可演示版本，與憲法不衝突。

## Out of Scope (W1 D1)

- Temporal Anchoring（解析「最近兩季」等期間語意）— R2 W2 D6
- 任何節點呼叫真實 LLM／embedding／retriever — R3/R4 W1 D2+
- Retry／指數回退／LLMLingua token 壓縮 — R2 W2 D7–8
- ColPali 多模態檢索與 Rerank 整合 — R3/R4 W2
- 4-way Hybrid Retrieval — R3 W1 D3 後續
- 雲端部署（Cloud Run／BigQuery 後端切換）— R2 W4 D20–22
