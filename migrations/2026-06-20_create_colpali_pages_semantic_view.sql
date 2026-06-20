-- Migration: 建立 polaris_core.v_colpali_pages_semantic
--            （colpali_pages 補 event_key / source_key / published_year /
--            published_month / published_yyyymm 屬性，再 LEFT JOIN
--            company_dim / r6_disclosure_event / r6_quarter /
--            r6_news_source_whitelist 的單一 view）
-- Date:      2026-06-20
-- Author:    Jenny
-- SOP:       CREATE OR REPLACE VIEW，不改動 colpali_pages 本表，無需
--            ALTER/UPDATE polaris_core 既有資料，可重跑、可直接 DROP VIEW 回退。
--            走 docs/協作開發環境_SOP_v1.md §7（R2 審查 / R1 核准 / R4 或 R1
--            套用，套用端需 BQ_ALLOW_CORE_WRITE=1 + dataset WRITER）。
-- Scope:     polaris-desk-team.polaris_core.v_colpali_pages_semantic（新建 view）
-- 依賴：     r6_disclosure_event / r6_quarter / r6_news_source_whitelist 已由
--            migrations/2026-06-18_create_r6_ontology.sql 建好（唯讀 join，不動該檔）。
--
-- 背景：colpali_pages 現存資料皆為法說會（earnings call）簡報頁（doc_type 唯一值
--   'presentation'，5701 列，20 檔 ticker），來源皆為公司 IR 官網
--   （同 migrations/2026-06-18_colpali_pages_add_event_source_published_attrs.sql
--   的回填常數）。本表目前只有 published_at（DATE），缺乏 event/source 維度標籤與
--   可直接 GROUP BY 的年/月欄位。比照 v_chunk_semantic 做法，於 view 內直接算出
--   event_key / source_key，不依賴該 ALTER 遷移是否已套用到 colpali_pages 本表，
--   故本 view 為獨立、冪等、可隨時 CREATE OR REPLACE。
--   刻意排除 colpali_pages.embedding 大欄位，供 RAG/頁面引用 metadata 顯示用。
--
-- ⚠️ 套用者請知悉：
--   1. CREATE OR REPLACE VIEW 為冪等操作，重複套用安全。
--   2. event_key / source_key 此處皆為常數回填，因現存資料來源單一
--      （法說會簡報、公司 IR 官網）；未來若新增其他來源/事件類型的頁面，
--      需先擴充本檔判斷邏輯再套用，不可沿用本檔常數覆蓋未知的 doc_type。

CREATE OR REPLACE VIEW `polaris-desk-team.polaris_core.v_colpali_pages_semantic`
OPTIONS(description='供 RAG / 頁面截圖引用 metadata 顯示；不含 embedding。')
AS
WITH pages_tagged AS (
  SELECT
    page_id,
    ticker,
    fiscal_period,
    doc_type,
    source_file,
    page_num,
    event_date,
    published_at,
    n_patches,
    fetched_at,
    'earnings_call' AS event_key,
    'PRIMARY_COMPANY_IR' AS source_key,
    EXTRACT(YEAR FROM published_at) AS published_year,
    EXTRACT(MONTH FROM published_at) AS published_month,
    CAST(FORMAT_DATE('%Y%m', published_at) AS INT64) AS published_yyyymm
  FROM `polaris-desk-team.polaris_core.colpali_pages`
)
SELECT
  p.page_id,
  p.ticker,
  c.company_name,
  c.industry_name,
  p.doc_type,
  p.fiscal_period,
  q.year,
  q.quarter,
  p.source_file,
  p.page_num,
  p.event_date,
  p.published_at,
  p.published_year,
  p.published_month,
  p.published_yyyymm,
  p.n_patches,
  p.fetched_at,
  p.event_key,
  d.event_type,
  d.event_type_name,
  d.event_subtype,
  d.event_subtype_name,
  d.category AS event_category,
  d.severity AS event_severity,
  p.source_key,
  w.source_name,
  w.trust_tier,
  w.allowed_for_fact,
  w.citation_required
FROM pages_tagged p
LEFT JOIN `polaris-desk-team.polaris_core.company_dim`             c USING (ticker)
LEFT JOIN `polaris-desk-team.polaris_core.r6_disclosure_event`     d USING (event_key)
LEFT JOIN `polaris-desk-team.polaris_core.r6_quarter`              q USING (fiscal_period)
LEFT JOIN `polaris-desk-team.polaris_core.r6_news_source_whitelist` w USING (source_key);

-- ── 套用後驗證（預期 5701，且新欄位皆無 NULL）─────────────────────────────
-- SELECT COUNT(*) AS n,
--        COUNTIF(event_key IS NULL) AS null_event_key,
--        COUNTIF(source_key IS NULL) AS null_source_key,
--        COUNTIF(published_year IS NULL) AS null_year,
--        COUNTIF(published_month IS NULL) AS null_month,
--        COUNTIF(published_yyyymm IS NULL) AS null_yyyymm
-- FROM `polaris-desk-team.polaris_core.v_colpali_pages_semantic`;
-- 接地：LEFT JOIN 對唯一鍵，不應放大列數；若放大代表維度有重複鍵。
-- event_key='earnings_call' 存在於 r6_disclosure_event seed（PR #104），
-- source_key='PRIMARY_COMPANY_IR' 存在於 r6_news_source_whitelist，
-- 故 event_type_name / source_name 等預期全部非 NULL。
