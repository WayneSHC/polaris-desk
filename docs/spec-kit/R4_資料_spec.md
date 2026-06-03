# 角色規格書（Spec Kit）：R4 — 資料工程師

**Role**: R4 Ingestion + 向量庫（BigQuery 為主，pgvector fallback）+ ColPali + 新聞 **色**：草綠
**對應**：專題 spec FR-001/002/005；4 週計畫 R4 卡 **Status**: Draft

## 1. Mission
把倉庫蓋好、把貨搬進去：把 100 份法說稿入 **BigQuery 共用 canonical `polaris_core`**（embedding 算一次、全員共用）；W3 上 ColPali + 新聞第 5 路 + 餵 Watchdog 事件；W4 部署 + 離線備援（pgvector）。
- **In scope**：PDF 解析 / 切塊 / embedding / 入庫、`VectorStore`（bigquery 主 / pgvector fallback）、多產業 schema、MOPS 爬蟲、ColPali、新聞表、Watchdog 事件來源、離線備援資料。
- **Out of scope**：檢索邏輯（R3）、編排（R2）、Ontology 內容（R6 主，R4 灌庫）。

## 2. Deliverables & Acceptance Criteria

| 交付物 | 對應 | 可驗收標準（measurable）|
|---|---|---|
| 100 份入庫（BigQuery `polaris_core`）| FR-001/G1 | 100 份法說稿成功入 `polaris_core`、**可被 Retriever 查到**；多產業 `gics_classifications` schema 就緒 |
| pgvector fallback 驗證 | Q-03/G4 | 同一份 eval 在 pgvector 後端跑出**與 BigQuery 一致**的結果（離線備援可切）|
| ColPali POC → 上線 | US3/TD-01/G3 | **圖表題檢索命中率 ≥ 70% 才採用**，否則砍（記 TD-01）|
| 新聞第 5 路 | FR-082/G3 | 新聞表入庫 + 成為第 5 路檢索來源 |
| Watchdog 事件來源 | FR-004 | MOPS 新公告 → 觸發 Watchdog（事件驅動）|
| 離線備援資料集 | SC-005/G4 | demo 用乾淨資料集 + mock ReAct trace JSON，斷網可跑 |

## 3. Tasks by Week（可勾選）

**W1**
- [ ] D1 **BigQuery `polaris_core` 建表**（依 SOP §4：分區 + cluster + 向量索引）；pgvector fallback 設定留待離線備援
- [ ] D2 Ingestion v0：1 份 PDF 成功入庫
- [ ] D3 法說稿 ingest：批次解析 + 切塊 + 算 embedding
- [ ] D4 100 份 ingest 全入 + 多產業 schema 調整
- [ ] D5 G1 驗收（入庫面）

**W2**
- [ ] D6 Embedding refresh（**前提：TD-01 已鎖定嵌入模型 `gemini-embedding-2`**）
- [ ] D7 MOPS 爬蟲
- [ ] D8 結構化財報
- [ ] D9 ColPali POC（圖表題命中率 ≥ 70% 才採用，否則砍 → 記 TD-01）
- [ ] D10 **BigQuery e2e 檢索驗收（Q-03）** → G2 驗收（資料面）

**W3（+2 人天）**
- [ ] D11–12 檢索調校 + 入庫監控
- [ ] D13 **ColPali 上線**：圖表檢索進正式環境
- [ ] D14 **Watchdog 事件接入**：MOPS 新公告 → 觸發
- [ ] D15–16 新聞表入庫 + 第 5 路 retrieval（FR-082）

**W4**
- [ ] D18 Watchdog 事件來源穩定化
- [ ] D21 供部落格 3（event-driven 資料管線）內容
- [ ] D24 **離線備援資料集**就緒（G4 條件）
- [ ] D26–27 備援資料 + mock ReAct trace JSON 檢驗

## 4. Dependencies
- **上游**：R6（Ontology / 首批 20 家公司 / 新聞白名單）、R2（向量庫後端切換取捨）、TD-01 鎖定。
- **下游**：R3 的檢索靠你的庫；R3 的 Watchdog 靠你的事件；R7 的離線 demo 靠你的備援資料。

## 5. Risks & Fallback
- ColPali 命中率 < 70% → 砍 ColPali（連帶場景 3），檢索退 BM25+向量+Rerank（記 TD-01）。
- pgvector fallback → 用匯出向量、不重算 embedding（省 token）即可在離線環境重建；Demo Day 斷網切回。
- **pgvector 效能三條雷**（已寫進 `init_pgvector.sql` 註解）：cosine 必須用 `<=>`、`ORDER BY <=> LIMIT k` 才走索引（EXPLAIN 確認 Index Scan）、filtered 查詢開 `iterative_scan`/`ef_search`。

## 6. Constitution 遵循
- **III**：金鑰不進 git；爬蟲取得的 PDF / 新聞**只供研究、不對外散布**（Q-09）。
- **VI**：嵌入用 `gemini-embedding-2`（768 維、cosine）；上雲 BigQuery 維度 / 距離須一致並重跑 eval 驗證。
