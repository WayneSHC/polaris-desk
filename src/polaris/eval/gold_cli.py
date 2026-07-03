"""CLI：``python -m polaris.eval.gold_cli [--no-generation] [gold.csv]``。

跑 gold set → 檢索分（token=0，always）+ 生成分/失敗分類（--no-generation 可略）→ Markdown。
無 active_retriever（CI/無金鑰）→ 檢索誠實缺席、生成走 stub workflow。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from polaris.eval.gold import load_gold_set
from polaris.eval.gold_report import render_gold_markdown
from polaris.eval.gold_score import run_generation
from polaris.eval.retrieval import run_retrieval

DEFAULT_GOLD = Path(__file__).resolve().parent / "data" / "gold_eps_2026Q1_v1.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m polaris.eval.gold_cli")
    parser.add_argument("gold", nargs="?", default=str(DEFAULT_GOLD))
    parser.add_argument("--quick", type=int, metavar="N", default=0, help="只抽前 N 題")
    parser.add_argument("--no-generation", action="store_true", help="只跑檢索分（省 LLM）")
    parser.add_argument(
        "--company-filter", action="store_true",
        help="每題帶 {'company': ticker} 檢索（pipeline 實況）；預設不帶（量原始鑑別力）",
    )
    parser.add_argument(
        "--corpus-rows", type=int, metavar="N", default=None,
        help="現況 v_chunk_semantic 全量 row 數；提供才做快照漂移守門（別用 BM25 工作集長度）",
    )
    parser.add_argument(
        "--pace-seconds", type=float, metavar="S", default=0.0,
        help="題間停頓秒數（Cohere Trial key 限 10/min，設 ~7 讓整批都真的過 rerank；預設 0）",
    )
    args = parser.parse_args(argv)

    items = load_gold_set(args.gold)
    if args.quick:
        items = items[: args.quick]

    retrieval = run_retrieval(items, company_filter=args.company_filter, pace_seconds=args.pace_seconds)
    mode = "帶 company filter（pipeline 實況）" if args.company_filter else "無 filter（原始檢索鑑別力）"

    scores = None
    if not args.no_generation:
        rmap = {rec.item_id: rec for rec in retrieval}
        scores = run_generation(items, rmap)

    # 快照漂移守門只在明確提供 --corpus-rows 時做（BM25 工作集只含最新 2 期，
    # 拿它冒充 v_chunk_semantic 全量會誤報，故不自動填）。
    print(render_gold_markdown(items, retrieval, scores, live_corpus_rows=args.corpus_rows, mode=mode))
    return 0


if __name__ == "__main__":  # pragma: no cover — 由 CLI smoke 測 main()
    sys.exit(main())
