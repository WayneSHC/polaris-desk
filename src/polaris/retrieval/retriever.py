"""4-way 混合檢索骨架（@R3）。

v0/v1 先做低成本、確定性的 2-way 檢索：
- 不需要 Gemini / Cohere / BigQuery key
- 預設不呼叫外部 API
- BM25 keyword ranking 先可用
- Vector search 透過可注入的 embedding_fn + VectorStore.search 介面接入
- 回傳 SearchResult，讓 Writer 後續可以接 citation
- W2 再把 Cohere rerank / ColPali 接進來
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from rank_bm25 import BM25Okapi

from ..vectorstore import SearchResult, VectorStore, get_vector_store


EmbeddingFn = Callable[[str], list[float]]


_FALLBACK_CORPUS = [
    SearchResult(
        id="stub-2330-2025Q1-gm",
        content="台積電 2025Q1 法說摘要：毛利率受到匯率、產品組合與產能利用率影響。",
        score=0.0,
        company="2330",
        period="2025Q1",
        metadata={"source_id": "stub-2330-2025Q1-gm", "origin": "keyword_fallback"},
    ),
    SearchResult(
        id="stub-2330-2024Q4-revenue",
        content="台積電 2024Q4 法說摘要：營收成長主要來自高效能運算與 AI 相關需求。",
        score=0.0,
        company="2330",
        period="2024Q4",
        metadata={"source_id": "stub-2330-2024Q4-revenue", "origin": "keyword_fallback"},
    ),
    SearchResult(
        id="stub-2317-2025Q1-segment",
        content="鴻海 2025Q1 法說摘要：營收組成涵蓋消費智能、雲端網路、電腦終端與元件。",
        score=0.0,
        company="2317",
        period="2025Q1",
        metadata={"source_id": "stub-2317-2025Q1-segment", "origin": "keyword_fallback"},
    ),
]


def _token_list(text: str) -> list[str]:
    """Tokenize mixed Chinese/English finance text for deterministic BM25.

    The CJK branch adds short n-grams so queries like ``毛利率`` still match
    longer chunks such as ``毛利率受到匯率影響``.
    """
    tokens: list[str] = []
    for match in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", text.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", match):
            if len(match) <= 4:
                tokens.append(match)
            for size in (2, 3):
                tokens.extend(match[i : i + size] for i in range(len(match) - size + 1))
        else:
            tokens.append(match)
    return tokens


def _matches_filters(result: SearchResult, filters: dict | None) -> bool:
    if not filters:
        return True
    for key, value in filters.items():
        if value is None:
            continue
        if key == "company" and result.company != value:
            return False
        if key == "period" and result.period != value:
            return False
    return True


def _copy_result(result: SearchResult, *, score: float, origin: str) -> SearchResult:
    metadata = dict(result.metadata)
    metadata["origin"] = origin
    metadata["retrieval_channels"] = [origin]
    return SearchResult(
        id=result.id,
        content=result.content,
        score=score,
        company=result.company,
        period=result.period,
        metadata=metadata,
    )


def _normalize_vector_result(result: SearchResult) -> SearchResult:
    metadata = dict(result.metadata)
    metadata["origin"] = "vector"
    metadata["retrieval_channels"] = ["vector"]
    return SearchResult(
        id=result.id,
        content=result.content,
        score=float(result.score),
        company=result.company,
        period=result.period,
        metadata=metadata,
    )


def _merge_results(results: list[SearchResult]) -> list[SearchResult]:
    merged: dict[str, SearchResult] = {}
    for result in results:
        existing = merged.get(result.id)
        if existing is None:
            merged[result.id] = result
            continue

        channels = list(existing.metadata.get("retrieval_channels", []))
        for channel in result.metadata.get("retrieval_channels", []):
            if channel not in channels:
                channels.append(channel)

        winner = result if result.score > existing.score else existing
        metadata: dict[str, Any] = dict(winner.metadata)
        metadata["retrieval_channels"] = channels
        merged[result.id] = SearchResult(
            id=winner.id,
            content=winner.content,
            score=winner.score,
            company=winner.company,
            period=winner.period,
            metadata=metadata,
        )
    return list(merged.values())


@dataclass
class HybridRetriever:
    top_k: int = 8
    store: VectorStore | None = None
    embedding_fn: EmbeddingFn | None = None

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = get_vector_store()

    def _bm25_search(self, query: str, filters: dict | None) -> list[SearchResult]:
        candidates = [item for item in _FALLBACK_CORPUS if _matches_filters(item, filters)]
        query_tokens = _token_list(query)
        if not candidates or not query_tokens:
            return []

        corpus_tokens = [
            _token_list(f"{item.id} {item.company or ''} {item.period or ''} {item.content}")
            for item in candidates
        ]
        bm25 = BM25Okapi(corpus_tokens)
        bm25_scores = list(bm25.get_scores(query_tokens))
        raw_scores: list[float] = []
        for item_tokens, bm25_score in zip(corpus_tokens, bm25_scores, strict=True):
            overlap_score = len(set(query_tokens) & set(item_tokens)) / max(len(query_tokens), 1)
            raw_scores.append(float(bm25_score) if bm25_score > 0 else overlap_score)

        max_score = max(raw_scores) if raw_scores else 0.0

        ranked: list[SearchResult] = []
        for item, score in zip(candidates, raw_scores, strict=True):
            if score <= 0:
                continue
            normalized_score = (score / max_score) * 0.5 if max_score else 0.0
            ranked.append(_copy_result(item, score=normalized_score, origin="bm25"))
        return ranked

    def _vector_search(self, query: str, filters: dict | None) -> list[SearchResult]:
        if self.embedding_fn is None or self.store is None:
            return []
        try:
            query_embedding = self.embedding_fn(query)
            if not query_embedding:
                return []
            results = self.store.search(query_embedding, self.top_k, filters=filters)
        except Exception:  # noqa: BLE001 - vector backend is optional in D3; BM25 stays available
            return []
        return [_normalize_vector_result(result) for result in results]

    def retrieve(self, query: str, *, filters: dict | None = None) -> list[SearchResult]:
        """Retriever D3：BM25 keyword + optional vector search interface.

        Vector search is intentionally opt-in through ``embedding_fn`` so local
        tests and personal development do not spend API quota by accident.
        """
        query = (query or "").strip()
        if not query:
            return []

        ranked = _merge_results([
            *self._bm25_search(query, filters),
            *self._vector_search(query, filters),
        ])
        ranked.sort(key=lambda r: r.score, reverse=True)
        return ranked[: self.top_k]
