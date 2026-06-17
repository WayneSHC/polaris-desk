#!/usr/bin/env python3
"""把 polaris_dev_jenny.chunks_768 / chunks_3072 遷移進 polaris_core。

背景：polaris_core 目前是空 dataset（PR #68 的合併 migration 尚未實際套用）。
本腳本只搬 jenny 自己 ingest 出來的兩張表：

    polaris_dev_jenny.chunks_768  (768 維，1608 列)
      -> polaris_core.chunks                （canonical，SOP §4 schema）
    polaris_dev_jenny.chunks_3072 (3072 維，1608 列，違反憲法 768/cosine)
      -> polaris_core.chunks_pending_reembed （隔離表，同 PR #68 #1 的處理方式，
         原 3072 維向量保留供稽核，之後用 scripts/reembed_pending_chunks.py
         --source-dataset polaris_core --target-dataset polaris_core 重算成 768
         併入 polaris_core.chunks）

兩個目標表都用 ``INSERT ... SELECT ... WHERE chunk_id NOT IN (...)`` 寫入，
chunk_id 已存在則跳過 —— 可重跑。

寫 ``polaris_core`` 需 ``BQ_ALLOW_CORE_WRITE=1``（憲法 III / SOP §3.4，R1/R4 限定）。

用法：
    python scripts/migrate_jenny_chunks_to_core.py --dry-run   # 只盤點，不寫入
    python scripts/migrate_jenny_chunks_to_core.py             # 實際遷移
"""
from __future__ import annotations

import argparse
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from polaris.config import settings

SOURCE_DATASET = "polaris_dev_jenny"
CORE_DATASET = "polaris_core"

# canonical polaris_core.chunks schema（同 migrations/2026-06-12_polaris_core_initial_merge.sql
# A 段 + 2026-06-14_add_owner_confidential_bq.sql）
CANONICAL_CHUNKS_DDL = """
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.chunks` (
  chunk_id      STRING NOT NULL,
  ticker        STRING,
  doc_type      STRING,
  fiscal_period STRING,
  published_at  DATE,
  chunk_text    STRING,
  embedding     ARRAY<FLOAT64>,
  owner         STRING,
  confidential  BOOL
)
PARTITION BY published_at
CLUSTER BY ticker, doc_type
"""

# 隔離表：同 canonical 形狀，多一個 source_dataset 欄做稽核追蹤；embedding 是 3072 維
# 原始向量，留給 scripts/reembed_pending_chunks.py 重算成 768 後併入 chunks。
PENDING_REEMBED_DDL = """
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.chunks_pending_reembed` (
  chunk_id        STRING NOT NULL,
  ticker          STRING,
  doc_type        STRING,
  fiscal_period   STRING,
  published_at    DATE,
  chunk_text      STRING,
  embedding       ARRAY<FLOAT64>,
  owner           STRING,
  confidential    BOOL,
  source_dataset  STRING
)
PARTITION BY published_at
CLUSTER BY ticker, doc_type
"""

CANONICAL_COLUMNS = (
    "chunk_id, ticker, doc_type, fiscal_period, published_at, "
    "chunk_text, embedding, owner, confidential"
)


def _dim_guard(bq, table: str, expected_dim: int) -> int:
    """回傳 ARRAY_LENGTH(embedding) != expected_dim 的列數（應為 0）。"""
    row = list(bq.query(
        f"SELECT COUNTIF(ARRAY_LENGTH(embedding) != {expected_dim}) bad "
        f"FROM `{table}`"
    ).result())[0]
    return row["bad"]


def _pending_count(bq, src: str, dst: str, dst_table: str) -> int:
    row = list(bq.query(f"""
        SELECT COUNT(*) n
        FROM `{src}` s
        WHERE s.chunk_id NOT IN (
            SELECT chunk_id FROM `{dst}.{dst_table}`
        )
    """).result())[0]
    return row["n"]


def _migrate_chunks_768(bq, project: str, *, dry_run: bool) -> None:
    src = f"{project}.{SOURCE_DATASET}.chunks_768"
    dst_dataset = f"{project}.{CORE_DATASET}"
    dst = f"{dst_dataset}.chunks"

    print(f"\n=== chunks_768 -> {dst} ===")
    bad = _dim_guard(bq, src, 768)
    if bad:
        sys.exit(f"維度守門失敗：{src} 有 {bad} 列 embedding 不是 768 維，拒絕遷移")

    bq.query(CANONICAL_CHUNKS_DDL.format(project=project, dataset=CORE_DATASET)).result()

    pending = _pending_count(bq, src, dst_dataset, "chunks")
    print(f"待寫入：{pending} 列（{src} 中 chunk_id 尚未存在於 {dst}）")
    if dry_run or pending == 0:
        return

    bq.query(f"""
        INSERT INTO `{dst}` ({CANONICAL_COLUMNS})
        SELECT {CANONICAL_COLUMNS}
        FROM `{src}` s
        WHERE s.chunk_id NOT IN (SELECT chunk_id FROM `{dst}`)
    """).result()
    print(f"完成：{pending} 列已寫入 {dst}")


def _migrate_chunks_3072(bq, project: str, *, dry_run: bool) -> None:
    src = f"{project}.{SOURCE_DATASET}.chunks_3072"
    dst_dataset = f"{project}.{CORE_DATASET}"
    dst = f"{dst_dataset}.chunks_pending_reembed"

    print(f"\n=== chunks_3072 -> {dst} (隔離，待重算 768) ===")
    bad = _dim_guard(bq, src, 3072)
    if bad:
        sys.exit(f"維度守門失敗：{src} 有 {bad} 列 embedding 不是 3072 維，拒絕遷移")

    bq.query(PENDING_REEMBED_DDL.format(project=project, dataset=CORE_DATASET)).result()

    pending = _pending_count(bq, src, dst_dataset, "chunks_pending_reembed")
    print(f"待寫入：{pending} 列（{src} 中 chunk_id 尚未存在於 {dst}）")
    if dry_run or pending == 0:
        return

    bq.query(f"""
        INSERT INTO `{dst}` ({CANONICAL_COLUMNS}, source_dataset)
        SELECT {CANONICAL_COLUMNS}, '{SOURCE_DATASET}.chunks_3072'
        FROM `{src}` s
        WHERE s.chunk_id NOT IN (SELECT chunk_id FROM `{dst}`)
    """).result()
    print(f"完成：{pending} 列已寫入 {dst}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="只盤點，不寫入")
    args = parser.parse_args()

    if not args.dry_run and not settings.bq_allow_core_write:
        sys.exit("拒寫 polaris_core：需 BQ_ALLOW_CORE_WRITE=1（憲法 III，R1/R4 限定）")

    from google.cloud import bigquery  # 延遲 import（同 store 層慣例）

    bq = bigquery.Client(project=settings.gcp_project)

    _migrate_chunks_768(bq, settings.gcp_project, dry_run=args.dry_run)
    _migrate_chunks_3072(bq, settings.gcp_project, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
