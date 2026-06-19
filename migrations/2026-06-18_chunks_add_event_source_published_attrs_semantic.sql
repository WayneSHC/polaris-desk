-- Migration: 建立 polaris_core.v_chunk_semantic
--            （chunks 補 event_key / source_key / published_year /
--            published_month / published_yyyymm 屬性，再 LEFT JOIN
--            company_dim / r6_disclosure_event / r6_quarter /
--            r6_news_source_whitelist 的單一 view）
-- Date:      2026-06-18
-- Author:    Jenny
-- SOP:       CREATE OR REPLACE VIEW，不改動 chunks 本表，無需 ALTER/UPDATE
--            polaris_core 既有資料，可重跑、可直接 DROP VIEW 回退。
-- Scope:     polaris-desk-team.polaris_core.v_chunk_semantic（新建 view）
-- 依賴：     r6_disclosure_event / r6_quarter / r6_news_source_whitelist 已由
--            migrations/2026-06-18_create_r6_ontology.sql 建好（唯讀 join，不動該檔）。
--
-- 背景：chunks 現存 doc_type 僅 3 種（major_news 5232 / transcript 1608 /
--   news 45，無 presentation），缺乏 event/source 維度標籤與可直接 GROUP BY
--   的年/月欄位，補上後可與 R6 ontology event/source 字典對齊，並讓報表依
--   年月彙整不必每次 EXTRACT。event_key / source_key 依 doc_type 對映：
--     doc_type    -> event_key          / source_key
--     transcript  -> earnings_call      / PRIMARY_EC_TRANSCRIPT
--     major_news  -> major_news.others  / PRIMARY_MOPS
--     news        -> news               / SECONDARY_NEWS_MEDIA
--   刻意排除 chunks.embedding 大欄位，供 RAG 引用 metadata 顯示用。
--
-- ⚠️ 套用者請知悉：
--   1. CREATE OR REPLACE VIEW 為冪等操作，重複套用安全。
--   2. event_key / source_key 依現存 doc_type 詞彙做常數對映；若未來新增
--      其他 doc_type，CASE 不會命中，event_key / source_key 會落空（NULL），
--      需先擴充本檔對映表再套用，不可沿用本檔常數覆蓋未知的 doc_type。

CREATE OR REPLACE VIEW `polaris-desk-team.polaris_core.v_chunk_semantic`
OPTIONS(description='供 RAG 引用 metadata 顯示；不含 embedding。')
AS
WITH chunks_tagged AS (
  SELECT
    chunk_id,
    ticker,
    doc_type,
    fiscal_period,
    published_at,
    chunk_text,
    CASE doc_type
      WHEN 'transcript' THEN 'earnings_call'
      WHEN 'major_news' THEN 'major_news.others'
      WHEN 'news' THEN 'news'
    END AS event_key,
    CASE doc_type
      WHEN 'transcript' THEN 'PRIMARY_EC_TRANSCRIPT'
      WHEN 'major_news' THEN 'PRIMARY_MOPS'
      WHEN 'news' THEN 'SECONDARY_NEWS_MEDIA'
    END AS source_key,
    EXTRACT(YEAR FROM published_at) AS published_year,
    EXTRACT(MONTH FROM published_at) AS published_month,
    CAST(FORMAT_DATE('%Y%m', published_at) AS INT64) AS published_yyyymm
  FROM `polaris-desk-team.polaris_core.chunks`
)
SELECT
  ch.chunk_id,
  ch.ticker,
  c.company_name,
  c.industry_name,
  ch.doc_type,
  ch.fiscal_period,
  q.year,
  q.quarter,
  ch.published_at,
  ch.published_year,
  ch.published_month,
  ch.published_yyyymm,
  ch.chunk_text,
  ch.event_key,
  d.event_type,
  d.event_type_name,
  d.event_subtype,
  d.event_subtype_name,
  d.category AS event_category,
  d.severity AS event_severity,
  ch.source_key,
  w.source_name,
  w.trust_tier,
  w.allowed_for_fact,
  w.citation_required
FROM chunks_tagged ch
LEFT JOIN `polaris-desk-team.polaris_core.company_dim`             c USING (ticker)
LEFT JOIN `polaris-desk-team.polaris_core.r6_disclosure_event`     d USING (event_key)
LEFT JOIN `polaris-desk-team.polaris_core.r6_quarter`              q USING (fiscal_period)
LEFT JOIN `polaris-desk-team.polaris_core.r6_news_source_whitelist` w USING (source_key);

-- ── 套用後驗證（預期 6885，且新欄位皆無 NULL）─────────────────────────────
-- SELECT COUNT(*) AS n,
--        COUNTIF(event_key IS NULL) AS null_event_key,
--        COUNTIF(source_key IS NULL) AS null_source_key,
--        COUNTIF(published_year IS NULL) AS null_year,
--        COUNTIF(published_month IS NULL) AS null_month,
--        COUNTIF(published_yyyymm IS NULL) AS null_yyyymm
-- FROM `polaris-desk-team.polaris_core.v_chunk_semantic`;
-- 依 doc_type 抽樣核對對映是否正確：
-- SELECT doc_type, event_key, source_key, COUNT(*) AS n
-- FROM `polaris-desk-team.polaris_core.v_chunk_semantic`
-- GROUP BY doc_type, event_key, source_key;
-- 接地：LEFT JOIN 對唯一鍵，不應放大列數；若放大代表維度有重複鍵。
-- event_key 三值（earnings_call/major_news.others/news）皆存在於 r6_disclosure_event
-- seed（10 列，PR #104），故 event_type_name 等預期全部非 NULL。
