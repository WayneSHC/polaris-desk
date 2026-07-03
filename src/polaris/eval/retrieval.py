"""檢索-only 評測（token=0，不碰 LLM）。

拿 gold 的 ``must_cite_chunk_id`` 當 relevant set，量 :class:`HybridRetriever` 的
``retrieve_candidates()``（rerank 前）vs ``retrieve()``（rerank 後）——把**檢索**這段
從 end-to-end 抽離，一題掛了才分得清是檢索沒撿回還是生成沒用好。

``SearchResult.id == chunk_id``（見 ``vectorstore/bigquery_store.py``）→ 直接比對。

無 ``active_retriever()``（CI / 無金鑰）→ 各題回 ``retriever_available=False``、指標 None，
誠實缺席，不假分。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from polaris.eval.gold import GoldItem

#: 預設回報的 k（retriever 預設 top_k=8 → 5/10 兩檔涵蓋 rerank 前後視窗）。
DEFAULT_KS: tuple[int, ...] = (5, 10)


@dataclass
class RetrievalRecord:
    """單題檢索結果 + 指標（pre = rerank 前候選、post = rerank 後）。"""

    item_id: str
    answerable: str
    retriever_available: bool = True
    gold_chunks: tuple[str, ...] = ()
    pre_ids: list[str] = field(default_factory=list)
    post_ids: list[str] = field(default_factory=list)
    #: recall@k：{k: 命中 gold 比例}；分母 = |gold|。
    recall_pre: dict[int, float] = field(default_factory=dict)
    recall_post: dict[int, float] = field(default_factory=dict)
    #: hit@k：top-k 內是否至少一個 gold。
    hit_post: dict[int, bool] = field(default_factory=dict)
    mrr_post: float = 0.0
    #: rerank 把第一個 gold 的排名推前幾名（+ = 推上來、- = 埋掉、0 = 沒動/都沒中）。
    rerank_delta: int = 0


def _first_rank(ids: list[str], gold: set[str]) -> int | None:
    """第一個命中 gold 的 1-based 排名；沒中回 None。"""
    for i, cid in enumerate(ids, 1):
        if cid in gold:
            return i
    return None


def _recall_at(ids: list[str], gold: set[str], k: int) -> float:
    if not gold:
        return 0.0
    return len(gold & set(ids[:k])) / len(gold)


def _mrr(ids: list[str], gold: set[str]) -> float:
    rank = _first_rank(ids, gold)
    return 1.0 / rank if rank else 0.0


def score_item(
    item: GoldItem,
    retriever,
    *,
    ks: tuple[int, ...] = DEFAULT_KS,
    filters: dict | None = None,
) -> RetrievalRecord:
    """跑單題檢索、算指標。``retriever=None`` → 誠實缺席。"""
    gold = set(item.must_cite_chunk_id)
    if retriever is None:
        return RetrievalRecord(
            item_id=item.item_id, answerable=item.answerable,
            retriever_available=False, gold_chunks=item.must_cite_chunk_id,
        )

    max_k = max(ks)
    pre = [s.id for s in retriever.retrieve_candidates(item.question, filters=filters, top_k=max_k)]
    post = [s.id for s in retriever.retrieve(item.question, filters=filters)]

    pre_rank = _first_rank(pre, gold)
    post_rank = _first_rank(post, gold)
    # rerank_delta：+ 表 rerank 把 gold 推前。任一側沒中 → 0（無法比較，不編故事）。
    delta = (pre_rank - post_rank) if (pre_rank and post_rank) else 0

    return RetrievalRecord(
        item_id=item.item_id,
        answerable=item.answerable,
        gold_chunks=item.must_cite_chunk_id,
        pre_ids=pre,
        post_ids=post,
        recall_pre={k: _recall_at(pre, gold, k) for k in ks},
        recall_post={k: _recall_at(post, gold, k) for k in ks},
        hit_post={k: bool(gold & set(post[:k])) for k in ks},
        mrr_post=_mrr(post, gold),
        rerank_delta=delta,
    )


def run_retrieval(
    items: list[GoldItem],
    *,
    retriever=None,
    ks: tuple[int, ...] = DEFAULT_KS,
    filters: dict | None = None,
    company_filter: bool = False,
) -> list[RetrievalRecord]:
    """批次檢索評測。``retriever=None`` → 取 ``active_retriever()``（CI/無金鑰時為 None）。

    兩種模式：
    - 預設（``company_filter=False``）：不帶公司 filter → 量**原始檢索鑑別力**
      （會暴露跨公司污染——近同的損益表頁在向量空間重疊）。
    - ``company_filter=True``：每題併入 ``{'company': item.company}`` → **pipeline 實況**
      （prod /ask 由實體解析導出同樣的 filter）。
    """
    if retriever is None:
        from polaris.retrieval.retriever import active_retriever

        retriever = active_retriever()

    out: list[RetrievalRecord] = []
    for it in items:
        item_filters = dict(filters or {})
        if company_filter and it.company:
            item_filters["company"] = it.company
        out.append(score_item(it, retriever, ks=ks, filters=item_filters or None))
    return out


@dataclass
class RetrievalSummary:
    """聚合分（只統計 answerable='Y' 且有 gold 的題；缺席題不入分母）。"""

    n_scored: int
    n_skipped_unavailable: int
    hit_post: dict[int, float]
    recall_pre: dict[int, float]
    recall_post: dict[int, float]
    mrr_post: float
    rerank_improved: int  # rerank_delta > 0 的題數
    rerank_hurt: int      # rerank_delta < 0 的題數


def summarize(records: list[RetrievalRecord], *, ks: tuple[int, ...] = DEFAULT_KS) -> RetrievalSummary:
    scored = [r for r in records if r.retriever_available and r.answerable == "Y" and r.gold_chunks]
    unavailable = sum(1 for r in records if not r.retriever_available)

    def _mean(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    return RetrievalSummary(
        n_scored=len(scored),
        n_skipped_unavailable=unavailable,
        hit_post={k: _mean([1.0 if r.hit_post.get(k) else 0.0 for r in scored]) for k in ks},
        recall_pre={k: _mean([r.recall_pre.get(k, 0.0) for r in scored]) for k in ks},
        recall_post={k: _mean([r.recall_post.get(k, 0.0) for r in scored]) for k in ks},
        mrr_post=_mean([r.mrr_post for r in scored]),
        rerank_improved=sum(1 for r in scored if r.rerank_delta > 0),
        rerank_hurt=sum(1 for r in scored if r.rerank_delta < 0),
    )


__all__ = [
    "DEFAULT_KS",
    "RetrievalRecord",
    "RetrievalSummary",
    "run_retrieval",
    "score_item",
    "summarize",
]
