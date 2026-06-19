-- Migration: 建立 polaris_core semantic layer（R6 於 canonical 之上的語意層 views）
-- Date:      2026-06-19
-- Author:    Jenny（內容 owner：R6；schema 審查：R2；核准：R1；套用：R4 或 R1）
-- SOP:       走 docs/協作開發環境_SOP_v1.md §7（R2 審查 / R1 核准 / R4 或 R1 套用，
--            套用端需 BQ_ALLOW_CORE_WRITE=1 + dataset WRITER）
-- Scope:     polaris-desk-team.polaris_core 新建 3 個 v_* views（唯讀，不動底層資料）
-- 依賴：     先套用 migrations/2026-06-18_create_r6_ontology.sql（需 r6_* 表）＋
--            既有 company_dim / chunks / financial_metrics。
-- 備註：     本檔基於 migrations/2026-06-18_create_r6_semantic_layer.sql 修訂而成。
--
-- 背景（跨角色決議，2026-06-18）：R6 直接在 polaris_core 建 semantic layer，把
--   facts（chunks / financial_metrics）與 R6 ontology 維度 join 成下游（R7 前端、
--   RAG metadata、Eval）可直接查的語意視圖，避免各角色重複 hardcode 對照。
--   ⚠️ R6 在 polaris_core 為 READER；view 仍是對 canonical 的 DDL 寫入，走 §7 PR，
--      由 R4 或 R1 套用。view 唯讀、可隨時 CREATE OR REPLACE，風險低。

-- ════════════════════════════════════════════════════════════════════════════
-- v_company_profile —— 公司主檔 + 主產業（company_dim 已含）+ 主題/次產業聚合
-- ════════════════════════════════════════════════════════════════════════════
CREATE OR REPLACE VIEW `polaris-desk-team.polaris_core.v_company_profile`
OPTIONS(description='公司語意主檔：company_dim + 聚合 themes + 次要產業。下游 R7/RAG 顯示用。')
AS
SELECT
  c.ticker,
  c.company_name,
  c.english_name,
  c.market,
  c.industry_id,
  c.industry_name,                                  -- 主產業（company_dim）
  c.is_financial,
  c.aliases,
  t.themes,                                         -- 逗號分隔 theme_name
  si.secondary_industries                           -- 逗號分隔次要產業
FROM `polaris-desk-team.polaris_core.company_dim` c
LEFT JOIN (
  SELECT ticker, STRING_AGG(DISTINCT theme_name, ', ' ORDER BY theme_name) AS themes
  FROM `polaris-desk-team.polaris_core.r6_company_theme_map`
  GROUP BY ticker
) t USING (ticker)
LEFT JOIN (
  SELECT ticker,
         STRING_AGG(DISTINCT industry_name, ', ' ORDER BY industry_name) AS secondary_industries
  FROM `polaris-desk-team.polaris_core.r6_company_industry_map`
  WHERE mapping_type != 'primary'
  GROUP BY ticker
) si USING (ticker);

-- ════════════════════════════════════════════════════════════════════════════
-- v_financial_metrics_semantic —— 財務事實 + 指標定義 + 公司名 + 季別對齊
-- ════════════════════════════════════════════════════════════════════════════
CREATE OR REPLACE VIEW `polaris-desk-team.polaris_core.v_financial_metrics_semantic`
OPTIONS(description='financial_metrics fact join 指標定義/公司/季別維度。零容錯數字校對與報表用。')
AS
SELECT
  f.ticker,
  c.company_name,
  f.fiscal_period,
  q.year,
  q.quarter,
  CASE
    WHEN f.event_key = 'monthly_revenue' THEN EXTRACT(MONTH FROM f.published_at)
    ELSE NULL
  END AS month,
  q.start_date AS period_start,
  q.end_date   AS period_end,
  f.metric_id,
  m.metric_name,
  m.category      AS metric_category,
  f.value,
  COALESCE(f.unit, m.unit) AS unit,
  m.zero_tolerance,                                 -- Y=零容錯金融數字
  f.source_id,
  f.published_at,
  f.event_key,
  d.event_type,
  d.event_type_name
FROM (
  SELECT
    *,
    CASE
      WHEN source_id LIKE '%monthly_revenue%' THEN 'monthly_revenue'
      WHEN source_id LIKE '%finmind%'        THEN 'earnings_call'
    END AS event_key
  FROM `polaris-desk-team.polaris_core.financial_metrics`
) f
LEFT JOIN `polaris-desk-team.polaris_core.company_dim`         c USING (ticker)
LEFT JOIN `polaris-desk-team.polaris_core.r6_financial_metric`  m USING (metric_id)
LEFT JOIN `polaris-desk-team.polaris_core.r6_quarter`           q USING (fiscal_period)
LEFT JOIN `polaris-desk-team.polaris_core.r6_disclosure_event`  d USING (event_key);

