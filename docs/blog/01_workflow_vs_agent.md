# Workflow 還是 Agent？Polaris Desk 的混合式架構抉擇

> Polaris Desk 技術部落格 · 系列 (1/2)
> 對應 R2 spec D19–20；技術細節皆可在本 repo 對照原始碼。

## 一句話的問題

「Multi-Agent」這四個字現在很好賣，但多數號稱 multi-agent 的系統，骨子裡是 **workflow**——一條人寫死的程式路徑去編排幾次 LLM 呼叫。這不是缺點，反而常常是對的選擇。真正的問題不是「要不要做 agent」，而是 **哪一段該用 workflow、哪一段該用 agent**。

我們在 Polaris Desk 做了一次誠實的盤點，最後落在一個**混合式**架構。這篇講為什麼。

## 兩個名詞，按 Anthropic 的定義

我們採用 Anthropic〈Building Effective Agents〉的區分，因為它最不含糊：

- **Workflow**：LLM 與工具被**預先寫好的程式路徑**編排。流程由你決定，LLM 只在固定的格子裡填空。可預測、可測試、好除錯。
- **Agent**：LLM **動態主導自己的流程與工具選擇**，自己決定下一步做什麼、何時停。彈性高，但每多一分自主，就多一分不可預測。

關鍵句：**自主性是成本，不是功勳。** 能用 workflow 解的就別用 agent——除非問題本身是開放式的、步數無法事先寫死。

## Polaris Desk 的主路徑＝確定性 Workflow

使用者問「台積電 2025Q1 毛利率變化」這類問題，步驟其實是固定的：規劃 → 檢索 → 計算 → 寫作 → 合規。我們就把它編成一條 **5 節點的 LangGraph workflow**（典型的 Orchestrator–Workers / prompt-chaining 模式）：

```
Planner → Retriever → Calculator → Writer → Compliance
（問題進）                                    （帶引用、過合規的答案出）
```

每個節點是一個「smart node」：有金鑰走 Gemini，無金鑰走確定性 fallback。這帶來幾個直接好處：

1. **可溯源**：每個節點都被 `@traced` 裝飾器記一筆 `NodeTrace`（節點名、狀態、耗時、輸入/輸出鍵）。整條 trace 就是答案怎麼來的證據鏈。
2. **可測試 / CI token-free**：fallback 模式讓整套流程不打任何 LLM 也能端到端跑，CI 一毛 token 都不花。
3. **可預測**：5 個節點、固定順序，沒有「LLM 今天想多跑三圈」的驚喜。

這條路徑**不需要**自主 agent。硬要套 agent 只會換來更難除錯、更貴、更不穩。

## 那 agent 用在哪？兩個真正開放式的地方

有些問題的步數**無法事先寫死**——這才是 agent 的主場。Polaris Desk 有兩個：

### 1. Deep Research Agent（自主 ReAct）
「比較台積電與聯發科最近兩季毛利率變化」這種同業比較題，要查幾次、查什麼、查到什麼程度才夠下結論，**事前不知道**。這裡我們放了一個真正的 agent：自寫的 **ReAct loop**（reason → act → observe），由 LLM 自己決定下一步是「再查一條」還是「可以收了」。但我們給它**硬邊界**：≤ 6 個迴圈、≥ 3 條引用才能 finish（直接編碼 FR-004）。自主，但有上限。（細節見系列第 2 篇。）

### 2. Watchdog Compliance Agent（事件驅動）
公開資訊觀測站（MOPS）冒出一則重大訊息時，要不要示警、嚴重程度多高，是事件驅動、開放式的判斷，也適合 agent。

## 一道閘，兩條路都得過：Compliance（NFR-031）

不管答案來自確定性 workflow 還是自主 agent，**最終輸出一律經過同一道 Compliance 閘**。這是我們的憲法級紅線 NFR-031：**系統只描述、標證據、標矛盾，絕不產出買賣建議**（投顧執照風險）。

這道閘是 defense-in-depth：

- **Layer 1（確定性 floor）**：6 個關鍵字（建議買進/建議賣出/加碼/減碼/看多/看空）永遠先跑、命中即收，LLM 永遠不能解除它。
- **Layer 2（Gemini 分類器）**：補抓關鍵字之外的隱性建議（「進場時機」「逢低布局」）。
- **fail-to-floor**：LLM 掛了就退回 floor，**絕不弱化保證**。LLM 只能「加攔」、永遠不能「改寫」答案。

把這道閘從各條路徑中抽出來、變成共用節點，意思是：**新增任何一條輸出路徑，都自動繼承同一套合規保證**，不會有人不小心漏接。

## 為什麼是混合，而不是「全 agent」

我們其實踩過坑。Polaris Desk 的 PRD v1.0 把自己行銷成 multi-agent，但做了一次 agentic audit 後發現：主體是 workflow，名不副實。v1.1 的修補不是「把全部改成 agent」，而是：

- 主路徑**誠實地**叫它 workflow（它就是，而且這樣最好）；
- 在**真正開放式**的兩個點補上**真的** agent（Deep Research、Watchdog）；
- 用一道共用 Compliance 閘把兩種路徑收斂在同一條合規底線上。

結論很樸素：**workflow 處理可預測的 80%，agent 只進駐無法寫死的 20%，合規閘罩住 100%。** 自主性花在刀口上，其餘地方用最便宜、最好測、最可溯源的方式做完。

---

下一篇：〈自己寫一個 ReAct Agent——為什麼我們不用 prebuilt，以及 ≤6 迴圈/≥3 引用怎麼來〉。
