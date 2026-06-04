"""4-way 混合檢索骨架（@R3）。

v0 先做低成本、確定性的關鍵字檢索：
- 不需要 Gemini / Cohere / BigQuery key
- 不呼叫外部 API
- 回傳 SearchResult，讓 Writer 後續可以接 citation
- W2 再把 BM25 / embedding / Cohere rerank / ColPali 接進來
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..vectorstore import SearchResult, get_vector_store


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


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,}", text.lower()))


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


@dataclass
class HybridRetriever:
    top_k: int = 8

    def __post_init__(self) -> None:
        self.store = get_vector_store()

    def retrieve(self, query: str, *, filters: dict | None = None) -> list[SearchResult]:
        """Retriever v0：低成本關鍵字 fallback。

        這版先解決「能接 query、能回 SearchResult」。
        真實 VectorStore / Gemini embedding / Cohere rerank 等 R4/R2 介面穩定後再接。
        """
        query = (query or "").strip()
        if not query:
            return []

        query_tokens = _tokens(query)
        ranked: list[SearchResult] = []

        for item in _FALLBACK_CORPUS:
            if not _matches_filters(item, filters):
                continue

            content_tokens = _tokens(item.content)
            overlap = query_tokens & content_tokens
            if not overlap:
                continue

            score = len(overlap) / max(len(query_tokens), 1)
            ranked.append(
                SearchResult(
                    id=item.id,
                    content=item.content,
                    score=score,
                    company=item.company,
                    period=item.period,
                    metadata=item.metadata,
                )
            )

        ranked.sort(key=lambda r: r.score, reverse=True)
        return ranked[: self.top_k]