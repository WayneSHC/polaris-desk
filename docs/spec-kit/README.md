# Polaris Desk — Spec Kit 規格書（per-role + 專題）

> 用 GitHub **Spec Kit**（spec-driven development）格式，把「PRD v1.1 + 4 週航程作戰計畫」
> 翻成**可驗收**的規格：每條任務都有**可量測的 Definition of Done**、明確依賴、對應閘門 / FR。
> 產出日 2026-05-31 · 對應 Spec Kit CLI v0.8.12。
>
> ✅ **本資料夾隨 GitHub repo 走，為「權威版」**（與 repo `.specify/memory/constitution.md` 同源）。
> Google Drive `Polaris Desk/03_規格書_PRD/spec-kit/` 為 PM 便讀鏡像；**改動以本 repo 版為準**，改完再同步回 Drive。

## 怎麼讀

1. 先讀 **`00_Polaris-Desk_專題_spec.md`** — 整個專題的 spec（憲法 + 4 個 demo 場景 = user stories + 功能需求 + 可量測成功標準 + 4 道閘）。
2. 再讀 **你自己那份** `R{n}_..._spec.md` — 你的任務、可驗收標準、依賴、降級方案。

## 檔案

| 檔 | 內容 |
|---|---|
| `00_Polaris-Desk_專題_spec.md` | 專題 spec + Constitution（不可違反原則）|
| `R1_PM_spec.md` | 產品願景 / Demo 劇本 / 進度治理 |
| `R2_架構師_spec.md` | LangGraph 編排 / Deep Research Agent / 上雲 |
| `R3_Agent_spec.md` | 4-way 檢索 / Writer 引用 / Watchdog Agent |
| `R4_資料_spec.md` | Ingestion / BigQuery（pgvector fallback）/ ColPali / 新聞 |
| `R5_Eval_spec.md` | Ragas / 三方 Judge / 130 題 ≥80% |
| `R6_金融品質_spec.md` | 台股 Ontology / 金融事實校對 / NFR-031 紅隊 |
| `R7_Demo全端_spec.md` | 前端 / 引用 UI / ReAct trace / 上雲部署 |

## Spec Kit 品質約定（每條需求都要過）

- **可量測（Measurable）**：完成標準是數字 / 可勾的事實，不是「polish / 穩定 / review」。
- **可驗收（Acceptance）**：用 *Given / When / Then* 或一個門檻描述「怎樣算過」。
- **可追溯（Traceable）**：對應到某個 FR / NFR / Go-No-Go 閘。
- **[NEEDS CLARIFICATION]**：還沒拍板的，明確標出來、附到期日與 owner，不要假裝已決。

> 這份是**活文件**：每週站會 / 過閘後更新；與 `00_開工包/4週航程作戰計畫.html`、
> `01_PM_Notion匯入/決策追蹤.csv`、`03_規格書_PRD/PRD v1.1.md` 互為對照。
