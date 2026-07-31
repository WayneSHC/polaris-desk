# 我們有 Ontology，但 Agent 沒在用：一次誠實的接線盤點

> Polaris Desk 技術部落格 · 系列 (4/4)
> 起點是一支影片：[Why Agentic Systems Need Ontologies — Frank Coyle, UC Berkeley](https://www.youtube.com/watch?v=Sir59K8ZDPU)（AI Engineer World's Fair）。
> 技術細節對照 `migrations/2026-06-18_create_r6_ontology.sql`、`src/polaris/ontology/`、`src/polaris/graph/compliance.py`。

## 為什麼這支影片值得寫一篇

Frank Coyle 的論點可以壓成一句話：**LLM 是機率性的文字產生器，它分不出「真」和「一個結構完美的幻覺」**。所以只要你的系統會 loop、會呼叫工具、會碰到真實交易，你就需要一層**確定性的護欄**——而那層護欄叫 ontology：一個把領域裡的實體、屬性、關係、約束寫死下來的形式規格。他把 agent + ontology 的合流稱為 **neuro-symbolic AI**：神經網路提供機率式的創造力，符號系統（knowledge graph、RDFS、OWL）提供確定性的約束。

聽到這裡我第一個反應不是「我們該做 ontology」，而是——**我們早就做了**。R6 交付的 `Ontology_V1` 已經落地成 `polaris_core` 裡 12 張 `r6_*` 維度表（`migrations/2026-06-18_create_r6_ontology.sql`）：產業階層、財務指標定義、揭露事件分類、法遵名詞、投資主題、風險訊號、新聞來源白名單⋯⋯全部走過 SOP §7 的 PR 審查流程。

所以真正該問的問題不是「要不要做 ontology」，而是一個難堪得多的問題：

> **這套 ontology，我們的 agent 真的在用嗎？**

我去把線一條一條拉出來看。答案是：**一半。而且是比較不重要的那一半。**

## 先講好消息：ontology 確實接上了「看板」

這不是一個「做完就丟」的故事。ontology 真的有被接進系統，接得還挺漂亮：

`v_chunk_semantic`（`migrations/2026-06-18_chunks_add_event_source_published_attrs_semantic.sql`）把 `chunks` 事實表跟四張維度表 join 起來——`company_dim`、`r6_disclosure_event`、`r6_quarter`、`r6_news_source_whitelist`——對外吐出 24 個欄位，包含 `company_name`、`industry_name`、`event_type_name`、`event_severity`，以及三個**專門為了可信度而存在**的欄位：`trust_tier`、`allowed_for_fact`、`citation_required`。

`v_financial_metrics_semantic` 同理，把 `financial_metrics` 接上 `r6_financial_metric`（指標定義）與 `r6_quarter`（季別對齊），所以 `/financials` 端點回傳的 `metric_name` 是**從 ontology 來的**，不是誰在 Python 裡硬打的字串（`src/polaris/structured_store.py:120`）。

這是對的做法。維度表在 BigQuery、語意層是 view、下游直接查——沒有人需要重複 hardcode 對照表。

## 壞消息：ontology 沒接進「大腦」

問題在於，上面接好的都是**顯示路徑**：使用者看到什麼名字、報表長什麼樣。而 agent 真正做決策的四個地方——**問句解析、檢索過濾、數字計算、法遵攔截**——一個都沒接。這四個地方全部走 Python 裡的硬編碼常數。

以下四個 gap，每一個我都在 repo 裡驗證過。

### Gap 1：ontology 知道 TSMC，agent 不知道

`company_dim` 有 `aliases` 欄位，`2330` 那列長這樣：

```
2330,台積電,Taiwan Semiconductor Manufacturing Company,上市,IND_FOUNDRY,晶圓代工,false,"台積電,TSMC,2330",22099131
```

ontology 明明白白知道 `TSMC` 就是 `2330`。但實際做實體解析的是 `src/polaris/ontology/companies.py:48` 的 `detect_tickers()`，它的比對邏輯是：

```python
for ticker, name in _COMPANY_NAMES.items():
    if (name and name in text) or (ticker in text):
```

**只比對 canonical 中文名和 4 碼代號，`aliases` 一眼都沒看。** 使用者打「TSMC 2025Q1 毛利率」，`detect_tickers` 回 `[]`。

回 `[]` 不是無害的。`src/polaris/retrieval/retriever.py:650` 的註解寫得很清楚：這個 ticker 清單是用來對每家公司加 `filters["company"]` 硬過濾，**避免語意相近的公司（聯電/聯詠、鴻海/台積電）純靠向量相似度混進來**——也就是 issue #77 那個 cross-company 污染 bug。偵測不到公司就不加過濾。

所以：**#77 修好了中文問句，英文簡稱問句的污染風險原封不動。** 而修它需要的資料，就躺在同一張表的隔壁欄位。

順帶一提，`_COMPANY_NAMES` 是一份 20 列的 Python dict——ontology 的**手抄副本**。`__init__.py` 的 docstring 誠實交代了原因：`docs/` 被 `.dockerignore` 排除，容器內讀不到 seed CSV，只好內嵌。他們還寫了 `tests/test_company_names.py` 守門防漂移。這是個負責任的 workaround，但它也解釋了為什麼 `aliases` 掉了——手抄的時候只抄了 name，沒抄 alias。

### Gap 2：可信度欄位算好了，查詢時沒拿

這個最可惜。`v_chunk_semantic` 已經幫每個 chunk 算好了 `trust_tier`（Primary/Secondary）、`allowed_for_fact`（Y/N）、`citation_required`（Y/N）——這三欄根本就是為了「這條證據能不能拿來當事實」而設計的。

而 `src/polaris/vectorstore/bigquery_store.py:129` 的檢索 SQL 是這樣選欄的：

```sql
SELECT vs.chunk_id, vs.chunk_text, vs.ticker, vs.fiscal_period,
       vs.doc_type, vs.published_at, vs.distance,
       sem.event_key, sem.source_key, sem.published_yyyymm
```

24 欄裡只拿了 3 欄，而且拿的是 `event_key` / `source_key` / `published_yyyymm`——**顯示用的 metadata**。`trust_tier`、`allowed_for_fact`、`citation_required` 一欄都沒取。

過濾條件更直接（`bigquery_store.py:37`）：

```python
_FILTER_COLUMNS = {
    "company": "ticker",
    "period": "fiscal_period",
    "doc_type": "doc_type",
}
```

三個維度，沒有一個跟可信度有關。意思是：**一則被 ontology 標成 `allowed_for_fact=N` 的二手新聞，和一份法說會逐字稿，在檢索排序裡是平等的**，誰的 cosine 距離近誰贏。

### Gap 3：法遵閘門有 6 個關鍵字，ontology 有 38 條

`src/polaris/graph/compliance.py` 是 NFR-031 的確定性底線——那個文件裡再三強調「LLM 永遠不能解除它」的 Layer 1：

```python
BUYSELL_KEYWORDS: tuple[str, ...] = (
    "建議買進", "建議賣出", "加碼", "減碼", "看多", "看空",
)
```

同一支檔案的 docstring 寫著：「**R6 W3 將：補完整關鍵字 / regex 集（含同義詞與否定句處理）**」。

R6 交了。`docs/r6/ontology/seeds/compliance_term.csv` 有 **38 條** compliance term，每條帶 `legal_basis`、`risk_pattern`、`forbidden_output`、`safe_response_rule`。光是前五列就包含這些 `forbidden_output`：

```
買進, 賣出, 加碼, 減碼, 目標價, 保證獲利
停損, 停利, 續抱, 抄底, 減碼
上看, 下看
```

拿去跟那 6 個關鍵字對一下，**確定性底線漏掉了：目標價、保證獲利、停損、停利、續抱、抄底、上看、下看。**

公平地說，這不代表系統會吐出買賣建議——Layer 2 的 Gemini 分類器就是設計來抓關鍵字之外的隱性建議，而且它抓得到「逢低布局」這類說法。但架構上的意思很明確：**我們把「絕對不能失守」的那條線，交給了會失守的那一層。** 底線本身反而是 ontology 的一個過期子集。

### Gap 4：指標怎麼算，寫在 Python 註解裡

`r6_financial_metric` 有 26 個指標，每個帶 `alias`、`formula_or_definition`、`unit`、`zero_tolerance`（是否零容錯金融數字）。

calculator 實際抓的是（`src/polaris/graph/nodes/stubs.py:237`）：

```python
_CALC_METRIC_IDS = ("revenue", "revenue_yoy", "gross_profit", "eps", "net_income")
```

5 個手挑的 id。上面那行還有一句註解：

```python
#: calculator 真路徑抓的 metric_id（gross_margin 非入庫指標，由 gross_profit / revenue 推導）。
```

**「由 gross_profit / revenue 推導」——這正是 `formula_or_definition` 這個欄位存在的意義。** ontology 裡 `gross_margin` 有定義、有單位、有零容錯標記；程式碼裡它是一句註解加一段散落的除法。

`zero_tolerance` 這個欄位尤其可惜。R6 明確標出了哪些數字**錯了就是重大事故**，而計算路徑完全不知道有這個分級——所有數字一視同仁。

## 為什麼會這樣？不是有人偷懶

盤完之後我的結論是：**這是結構問題，不是態度問題。** 有三個很具體的原因：

**一、ontology 的交付物是「資料」，不是「介面」。** R6 交的是 xlsx → CSV → BigQuery 表。資料放在那裡，但沒有任何一個 Python 函式簽名會因為 ontology 更新而改變，也沒有任何測試會因為「你沒用 ontology」而變紅。**沒有紅燈的規範，就只是文件。**

**二、`.dockerignore` 這種小事會決定架構。** `docs/` 被排除 → 容器讀不到 seed CSV → 只能內嵌 Python literal → 手抄時掉了 `aliases`。一行 ignore 規則，最後變成一個檢索污染風險。

**三、角色權限跟接線責任錯位。** R6 在 `polaris_core` 是 **READER**，連自己的 ontology 表都要走 §7 PR 請 R4/R1 代為套用。ontology 的 owner 沒有權限改 runtime，runtime 的 owner（R2/R3）沒有義務去讀 ontology。中間那段「把它接起來」，**沒有人的 spec 寫著它**。

這三點合起來就是 Coyle 那個論點的實務版註腳：ontology 不會因為「存在」就變成 guardrail。**它必須在 agent 做決定的那一行程式碼上生效，否則它只是一張很漂亮的試算表。**

## 那未來怎麼做會更好

我的建議是**分四階段、由低風險往高風險走**，而且有一條貫穿的設計原則。

先講那條原則，因為它決定了所有實作方式：

> **優先用 build-time 生成，而不是 runtime 查詢。**

理由是這個專案已經有的三條硬約束：CI 必須 token-free、fallback 路徑必須離線可跑、compliance 必須 100% 確定性。如果法遵閘門改成「每次呼叫去 query BigQuery」，這三條全破——而且引入了一個新的失敗模式（BQ 掛了，法遵閘門怎麼辦？fail-open 是災難，fail-closed 是全站停擺）。

正確做法是：**寫一個 codegen script，從 seed CSV 生出 Python 常數，commit 進 repo，CI 驗證生成物與 seed 一致。** 這樣 ontology 是單一事實來源，runtime 依然是確定性純函式、零外部依賴。這其實就是 `test_company_names.py` 已經在做的事——只是把它從「守門」升級成「生成」。

### 階段 0 — 接 `aliases`（幾行的事，先做）

`gen_ontology_seeds.py` 已經存在，擴充它同時生出 `_COMPANY_ALIASES`，讓 `detect_tickers()` 一併比對別名。

驗收：一題 `TSMC 2025Q1 毛利率` 的 eval，斷言檢索結果不含非 2330 的 chunk。這題現在應該是紅的——**先讓它紅，才證明修得有意義**。

風險極低，而且直接補上 #77 的英文缺口。

### 階段 1 — 法遵閘門由 ontology 生成

把 `BUYSELL_KEYWORDS` 從手寫 tuple 改成 codegen 產物，來源是 `compliance_term.csv` 的 `forbidden_output` 欄。

這一步**必須配紅隊 eval 一起上**：新增的每個詞（目標價、停損、停利、續抱、抄底、上看、下看、保證獲利）都要有對應紅隊題，而且要驗**誤攔率**——「這檔停利點設在哪」該攔，但「公司說明會提到庫存去化已停止」不該被「停」字誤傷。所以是 `forbidden_output` 逐詞比對，不是拆字。

這是四個 gap 裡**唯一直接關係到憲法紅線**的，優先度僅次於階段 0。

### 階段 2 — 檢索吃可信度

兩件事：SQL 多選 `trust_tier` / `allowed_for_fact` / `citation_required` 三欄；`_FILTER_COLUMNS` 加一個 `allowed_for_fact` 過濾鍵。

先**不要**預設開啟過濾——先把欄位帶進 `Citation.metadata`，跑一輪 eval 看看目前的答案裡有多少比例引用了 `allowed_for_fact=N` 的來源。**有數字再決定要過濾還是只降權**。這符合這個專案一貫的 flag-gated + 先觀測後開的作風。

### 階段 3 — 指標定義與零容錯分級

`_CALC_METRIC_IDS` 改成從 `financial_metric.csv` 生成；`gross_margin` 的推導規則從註解變成 ontology 欄位驅動；`zero_tolerance=Y` 的指標在 eval 裡走**更嚴的通過門檻**。

這一階段最大的價值不是「支援更多指標」，而是 `zero_tolerance`——讓系統知道哪些數字錯了是重大事故，並據此調整 fallback 策略（零容錯指標算不出來，寧可誠實說沒有，也不要推導一個近似值）。

### 階段 4 — 真正的 ontology 用法：一致性檢查

前三階段本質上都還是「把 ontology 當設定檔用」。Coyle 講的 neuro-symbolic 有更進一步的東西：**用 ontology 的關係去驗證 agent 的輸出是不是語意上可能**。

`r6_risk_signal` 有 `related_metric_id` 和 `related_event_id` 兩個外鍵——這是現成的關係圖。可以做的檢查像是：

- agent 說某公司有某個風險訊號，但引用的證據裡沒有對應的 `related_metric_id` 指標 → 標記為未接地
- 一則 chunk 被歸到 `event_type=earnings_call`，但 `fiscal_period` 跟 `r6_quarter` 的日期區間對不上 → 資料矛盾
- peer-compare 拿兩家公司比，但兩者在 `r6_company_industry_map` 沒有共同產業 → 這個比較本身可疑

這才是 ontology 作為 guardrail 的完整形態：**不只約束輸入，還驗證輸出**。這也是投入產出比最不確定的一階段，我會放最後，等前三階段的數字出來再評估。

## 一個必要的但書

我不覺得 ontology 是銀彈，這篇也不該被讀成「加了 ontology 就不會幻覺」。

ontology 能擋的是**語意上不可能**的錯誤——不存在的指標、對不上的季別、白名單外的來源、明確禁止的措辭。它擋不了**語意上可能但事實上錯誤**的東西：一個格式完美、引用有效、指標存在、季別正確，但數字抄錯的句子。那種錯誤要靠接地閘門（`is_traceable_prose` / `numbers_grounded`）和 eval 抓，跟 ontology 是兩條正交的防線。

而且 ontology 本身也會錯、會過期。`r6_company_industry_map` 的 `revenue_pct` 目前多數是 NULL，`compliance_term` 的 38 條也不可能窮盡所有講法。**把 ontology 接進 runtime，等於把「ontology 的正確性」升級成上線風險**——這是真實的成本，換來的是它終於能發揮作用。這筆交易我認為划算，但它是一筆交易，不是免費的。

## 收尾

回到 Coyle 那句話：LLM 分不出真相和一個結構完美的幻覺，所以你需要確定性的護欄。

我們專案的版本是：**我們蓋好了護欄，然後把它放在停車場，車照樣開在沒有護欄的路上。**

12 張維度表、38 條法遵名詞、26 個指標定義、24 欄語意視圖——這些全都做完了、審過了、上線了。缺的不是 ontology，是**四段接線**：`aliases` 進實體解析、`forbidden_output` 進法遵底線、`allowed_for_fact` 進檢索、`formula_or_definition` 進計算。

前兩段是幾十行程式碼加對應的 eval 題。這大概是這個專案裡投入產出比最高的一塊工作——因為最貴的部分（把領域知識形式化）R6 已經付過了。

---

**參考來源**

- [Why Agentic Systems Need Ontologies — Frank Coyle, UC Berkeley（AI Engineer World's Fair）](https://www.youtube.com/watch?v=Sir59K8ZDPU)
- [Ontologies Are So Back: Why AI Agents Are Reviving the Semantic Web — Latent Space](https://www.latent.space/p/ontologies-agentic-systems)
- [Agentic AI Needs Ontologies for Guardrails, Says UC Berkeley Expert — StartupHub.ai](https://www.startuphub.ai/ai-news/artificial-intelligence/2026/agentic-ai-needs-ontologies-for-guardrails-says-uc-berkeley-expert)
- [Why Agentic Systems Need Ontologies — Decision Management Community](https://dmcommunity.org/2026/07/28/why-agentic-systems-need-ontologies/)

本文所有 repo 內的指涉皆可對照原始碼：`migrations/2026-06-18_create_r6_ontology.sql`、`migrations/2026-06-18_chunks_add_event_source_published_attrs_semantic.sql`、`src/polaris/ontology/companies.py`、`src/polaris/vectorstore/bigquery_store.py`、`src/polaris/graph/compliance.py`、`src/polaris/graph/nodes/stubs.py`、`docs/r6/ontology/seeds/*.csv`。
