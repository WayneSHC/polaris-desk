-- Migration: 建立 polaris_dev_wayne_staging.chunks_0617_v1_semantic（向量檢索語意層 view）
-- Date:      2026-06-17
-- Author:    Jenny
-- SOP:       個人 dev staging dataset（polaris_dev_wayne_staging），非 polaris_core，
--            不走 §7 PR；單純 CREATE OR REPLACE VIEW，可重跑、可直接 DROP VIEW 回退。
-- Scope:     polaris-desk-team.polaris_dev_wayne_staging.chunks_0617_v1_semantic（新建 view）
--
-- 背景：chunks_0617_v1（6885 chunks，doc_type = major_news/transcript/news）只有
--   chunk_id / ticker / doc_type / fiscal_period / published_at / chunk_text /
--   embedding / owner / confidential，要做 vector search 的語意層需要額外的
--   公司、產業、主題維度，依 R6 Ontology_V1.2 資料字典（docs\r6\data_dictionary\
--   Ontology_V1.2_資料字典暨協作手冊.docx）規則，以 ticker 為 V1.1 正式 join key
--   接 02_company / 08_company_theme_mapping / 09_company_industry_mapping。
--
-- Join key：ticker（V1_1_JOIN_KEY_TICKER，2026-06-09 治理決議）。
--
-- 已知限制（waived，2026-06-17 確認）：
--   1. 04_disclosure_events 無法接：chunks_0617_v1 已移除 event_id 欄位，且
--      doc_type 詞彙（major_news/transcript/news）與 event_id 詞彙
--      （earnings_call/dividend/board_meeting…）不對應，故本版不含
--      event_name / category / severity。
--   2. 10_news_source_whitelist 無法接：chunks_0617_v1 已移除
--      doc_source_name / doc_source_url，雖然 76% 列為 major_news/news，
--      仍無法判斷來源可信度（trust_tier / citation_required / allowed_for_fact）。
--      若需引用接地（NFR-031 相關），需先請上游在 chunks_0617_v1 補回來源欄位。
--   3. 09/08 mapping 為 ticker 對多列（one-to-many），故用 ARRAY_AGG 先在子查詢
--      依 ticker GROUP BY 收斂成 1 列，避免 JOIN 後 chunk_id 被乘積展開
--      （驗證：chunks_0617_v1_semantic 與來源表的 distinct chunk_id 數一致）。
--   4. chunks_0617_v1 來源表本身已有 9 筆重複 chunk_id（total 6885 / distinct 6876），
--      與本 view 的 join 無關，屬上游 ingestion 既有資料品質問題。

CREATE OR REPLACE VIEW `polaris-desk-team.polaris_dev_wayne_staging.chunks_0617_v1_semantic` AS
WITH industries AS (
  SELECT
    ticker,
    ARRAY_AGG(STRUCT(industry_id, industry_name, mapping_type) ORDER BY primary_rank) AS industries
  FROM `polaris-desk-team.polaris_dev_wayne.r6_ontology__09_company_industry_mapping`
  GROUP BY ticker
),
themes AS (
  SELECT
    ticker,
    ARRAY_AGG(STRUCT(theme_id, theme_name, priority) ORDER BY priority) AS themes
  FROM `polaris-desk-team.polaris_dev_wayne.r6_ontology__08_company_theme_mapping`
  GROUP BY ticker
)
SELECT
  c.*,
  comp.company_name,
  comp.english_name,
  comp.market,
  comp.is_financial,
  i.industries,
  t.themes
FROM `polaris-desk-team.polaris_dev_wayne_staging.chunks_0617_v1` c
LEFT JOIN `polaris-desk-team.polaris_dev_wayne.r6_ontology__02_company` comp USING (ticker)
LEFT JOIN industries i USING (ticker)
LEFT JOIN themes t USING (ticker);

-- ── 套用後驗證（預期 total = distinct_chunks，即 join 沒有展開列數）──────────
-- SELECT COUNT(*) AS total, COUNT(DISTINCT chunk_id) AS distinct_chunks
-- FROM `polaris-desk-team.polaris_dev_wayne_staging.chunks_0617_v1_semantic`;
-- 抽樣檢查多值 industries / themes（2317 鴻海應有 3 個 industries、4 個 themes）：
-- SELECT ticker, company_name, industries, themes
-- FROM `polaris-desk-team.polaris_dev_wayne_staging.chunks_0617_v1_semantic`
-- WHERE ticker = '2317' LIMIT 1;
