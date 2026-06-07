# Design：`fetch-tw-earnings-call` skill

> 把抓台股法說會資料做成可跨股票代號的 skill：中英文法說會**簡報（presentation）**與
> **逐字稿（transcript）**，繞過公開資訊觀測站（MOPS）反爬，直接打權威來源。
> 起點＝既有 `scripts/fetch_ctbc_earnings_call.py`（中信金 2891 專用）。

- **日期**：2026-06-07
- **狀態**：設計待實作
- **接地對齊**：[`docs/R4_資料下載清單.md`](../../R4_資料下載清單.md)、`.specify/memory/constitution.md`（FR-003 引用接地）

---

## 1. 目標與非目標

**目標**
- 給定 `stock_id`（與選用年份範圍），下載該公司法說會**簡報**與**逐字稿**（有則抓），中英文皆收。
- 跨股票代號可用：未在 vendor 註冊表內的代號，仍能透過集中式來源拿到簡報。
- 每份檔案產出可溯源 metadata（manifest），供 R4 ingestion 後續灌入語料庫。

**非目標**
- 不解析 PDF、不切塊、不算 embedding（那是 R4 ingestion 的事，本 skill 只負責「下載 + 落地 + manifest」）。
- 不產任何分析或買賣建議（NFR-031 不適用於純下載，但 manifest 保留來源以利後續接地）。
- 不爬法說會「影音 / webcast」（YAGNI；未來可加 adapter）。

---

## 2. 架構（混合來源）

```
.claude/skills/fetch-tw-earnings-call/
├─ SKILL.md                     # 觸發說明 + 用法（給 agent/人）
└─ scripts/
   ├─ fetch_earnings_call.py    # 主入口（CLI）：解析 → 合併 → 去重 → 落地 → manifest
   ├─ model.py                  # Doc dataclass + 期別正規化 + 檔名產生器
   ├─ sources/
   │  ├─ mops.py                # 集中式底層：法人說明會一覽表（任意代號）
   │  └─ adapters/
   │     ├─ base.py             # Adapter 介面（協定）
   │     └─ todayir.py          # 第一個 vendor adapter（中信金等 TodayIR 站）
   └─ companies.py              # stock_id → {name, vendor, ir_config} 小註冊表
```

### 解析流程
給定 `stock_id`：
1. **Vendor adapter（richer，若註冊表命中）**：如 `2891 → todayir`。拿中文+英文簡報、有則 transcript。
2. **MOPS 底層（一律執行）**：法人說明會一覽表，補齊/交叉驗證；未知代號**只**走這層（仍拿得到簡報）。
3. **合併**：以 `(fiscal_period, doc_type, lang)` 為鍵合併兩來源；**用內容 md5 去重**（解決「同檔列兩次」問題）。
4. **落地 + 寫 manifest**。

### 元件邊界（各自可獨立測試）
| 元件 | 做什麼 | 依賴 |
|---|---|---|
| `model.Doc` | 一筆下載目標的值物件（ticker/date/lang/period/doc_type/url…）+ 檔名產生 | 無 |
| `model` 期別正規化 | `民國115/03`、`2026 第一季`、`1Q26` → `2026Q1` | 無 |
| `sources.mops` | 查 MOPS 法人說明會一覽表 → `list[Doc]` | network |
| `adapters.base` | `supports(stock_id)` / `fetch(stock_id, years) -> list[Doc]` 協定 | 無 |
| `adapters.todayir` | 解析 `ir.ctbcholding.com/c/financial_analyst?year=` → `list[Doc]` | network |
| `companies` | 代號→vendor 設定查表 | 無 |
| `fetch_earnings_call` | 編排：解析→合併→去重→下載→manifest | 上述全部 |

---

## 3. 輸出與命名

```
data/<stock_id>_<name>/
├─ <ticker>_<yyyymmdd><L><nnn>_<period>_concall_<doctype>.pdf
└─ manifest.json
```

**檔名規則**：`<ticker>_<yyyymmdd><L><nnn>_<period>_concall_<doctype>.pdf`
- `yyyymmdd`：**法說會舉行日**（取自簡報 PDF 首頁標示日期；無法取得時退回 MOPS 公告日，並於 manifest 標記 `date_source`）。
- `L`：語言旗標，`M`=中文、`E`=英文。
- `nnn`：流水號，依 `(ticker, yyyymmdd, L)` 從 `001` 起；同場次同語言有多檔（簡報+補充）才進 `002`。
- `period`：`YYYYQn`（如 `2026Q1`）。
- `doctype`：`presentation` | `transcript`。

例：`2891_20260519M001_2026Q1_concall_presentation.pdf`

**manifest.json**（每檔一筆，欄位對齊 R4 清單）：
```json
{
  "file": "2891_20260519M001_2026Q1_concall_presentation.pdf",
  "stock_id": "2891",
  "company": "中信金控",
  "doc_type": "presentation",
  "fiscal_period": "2026Q1",
  "lang": "zh",
  "event_date": "2026-05-19",
  "date_source": "pdf_first_page",
  "source_url": "https://media-ctbc.todayir.com/....pdf",
  "source_page": "https://ir.ctbcholding.com/c/financial_analyst?year=2026",
  "fetched_at": "2026-06-07",
  "md5": "…",
  "bytes": 1545741
}
```
> manifest 的 `lang` 用 `zh`/`en`（語意清楚）；檔名用 `M`/`E`（依使用者指定）。兩者一一對應。

---

## 4. Transcript 與中英文

- **中英文**：來源有出就兩版都抓。語言判定優先序：① adapter 已知的中英連結分流 → ② 檔名/連結標籤關鍵字 → ③ PDF 首頁語言偵測。
- **Transcript**：多數台股**不公開**逐字稿。策略＝**有才抓**；無則於執行摘要明確標註「此公司無公開 transcript」，manifest 不虛構、只列實際存在檔案。大型股（如 TSMC）官方英文 transcript 由其 adapter 處理。

---

## 5. 邊界與錯誤處理

- 代號查無法說會記錄 → 明確訊息、回傳非零、**非靜默成功**。
- 網路：瀏覽器 UA + per-request timeout + 有限重試 + 禮貌延遲。
- 跨來源/重複連結 → 內容 md5 去重。
- **MOPS 風險揭露**：改版後為 302 redirect / 前端 API（POST）。底層為**最不確定**之處；實作首步先實測現行端點（記錄於實作計畫）。
  - 緩解：MOPS 失敗時，**vendor adapter 命中的公司照常產出**；未知代號退化為「查無」並提示改用/新增 adapter。

---

## 6. 測試（pytest，Python 3.13）

純函式 / 解析以**存檔 HTML fixture** 測，網路呼叫不進測試：
- 期別正規化（民國/中文季/`1Q26` → `YYYYQn`）。
- 檔名產生器（流水號範圍、M/E、doctype）。
- md5 去重（同檔多連結只留一份）。
- `sources.mops` 解析（fixture）。
- `adapters.todayir` 連結抽取（fixture＝已存的 `financial_analyst?year=` HTML）。

---

## 7. 打包與相容

- **權威來源**：寫在專案 `polaris-desk/.claude/skills/fetch-tw-earnings-call/`（進 git、全隊共用）。
- **跨專案副本**：複製一份到 `~/.claude/skills/fetch-tw-earnings-call/`；專案版為準，更新時同步。
- **舊腳本**：`scripts/fetch_ctbc_earnings_call.py` 保留作參考（不改），其 todayir 邏輯移植進 `adapters/todayir.py`。
- **companies 註冊表初始內容**：固定 5 檔（2308/2317/2330/2454/3034）+ 2891；TodayIR 廠商者先連 `todayir` adapter，其餘僅走 MOPS 底層直到補上 adapter。

---

## 8. 未決 / 後續

- MOPS 現行端點細節 → 實作第一步實測後補入計畫。
- 其他 IR 廠商 adapter（每加一家擴一個 `adapters/<vendor>.py`）。
- 影音 / webcast 抓取（未來）。
