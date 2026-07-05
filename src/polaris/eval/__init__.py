"""Polaris Desk Eval pipeline（R5 / G3 硬門檻 Eval ≥ 80%）— 公開 API。

題庫 CSV → runner（workflow / Deep Research）→ smoke 達標率 + Ragas（optional）。
"""
from polaris.eval.dataset import EvalItem, load_dataset
from polaris.eval.gold import GoldItem, load_gold_set
from polaris.eval.gold_score import GoldScore, run_generation
from polaris.eval.retrieval import RetrievalRecord, run_retrieval, summarize
from polaris.eval.runner import EvalRecord, run_dataset, run_item
from polaris.eval.score import SmokeReport, smoke_score

__all__ = [
    "EvalItem",
    "EvalRecord",
    "GoldItem",
    "GoldScore",
    "RetrievalRecord",
    "SmokeReport",
    "load_dataset",
    "load_gold_set",
    "run_dataset",
    "run_generation",
    "run_item",
    "run_retrieval",
    "smoke_score",
    "summarize",
]
