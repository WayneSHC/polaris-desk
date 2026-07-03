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
    #: Cohere rerank 是否真的跑了（post 結果帶 origin=="rerank"）。False = 降級/缺 key/429，
    #: 此時 post==pre，rerank_delta 無意義 → 報 None（N/A），不偽裝成 0。
    rerank_ran: bool = False
    #: rerank 把第一個 gold 的排名推前幾名（+ = 推上來、- = 埋掉）。rerank 沒跑或任一側
    #: 沒中 → None（誠實 N/A，不編故事、不報 0）。
    rerank_delta: int | None = None


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


def _rerank_ran(results) -> bool:
    """post 結果是否真的過了 Cohere rerank。

    retriever 在 rerank 成功時給結果打 ``metadata["origin"]=="rerank"`` /
    ``retrieval_channels`` 含 "rerank"（見 retriever.py）；429 降級則保留 bm25/embedding
    origin。以此判別 rerank 有沒有真的跑，避免把「降級」當成「rerank 沒動排名」。
    """
    for r in results:
        meta = getattr(r, "metadata", None) or {}
        if meta.get("origin") == "rerank" or "rerank" in (meta.get("retrieval_channels") or []):
            return True
    return False


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
    post_results = list(retriever.retrieve(item.question, filters=filters))
    post = [s.id for s in post_results]
    rerank_ran = _rerank_ran(post_results)

    pre_rank = _first_rank(pre, gold)
    post_rank = _first_rank(post, gold)
    # rerank_delta：+ 表 rerank 把 gold 推前。rerank 沒真的跑（降級/缺 key/429）或任一側
    # 沒中 → None（無法比較，誠實 N/A，不報 0 假裝「中性」）。
    delta = (pre_rank - post_rank) if (rerank_ran and pre_rank and post_rank) else None

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
        rerank_ran=rerank_ran,
        rerank_delta=delta,
    )


def run_retrieval(
    items: list[GoldItem],
    *,
    retriever=None,
    ks: tuple[int, ...] = DEFAULT_KS,
    filters: dict | None = None,
    company_filter: bool = False,
    pace_seconds: float = 0.0,
) -> list[RetrievalRecord]:
    """批次檢索評測。``retriever=None`` → 取 ``active_retriever()``（CI/無金鑰時為 None）。

    兩種模式：
    - 預設（``company_filter=False``）：不帶公司 filter → 量**原始檢索鑑別力**
      （會暴露跨公司污染——近同的損益表頁在向量空間重疊）。
    - ``company_filter=True``：每題併入 ``{'company': item.company}`` → **pipeline 實況**
      （prod /ask 由實體解析導出同樣的 filter）。

    ``pace_seconds``：題間停頓秒數（預設 0 = 不停）。Cohere **Trial key** 限 10 calls/min，
    批次連打會 429 → rerank 降級 → 多數題 ``rerank_ran=False``。設 ~7 秒可壓在限額內，
    讓整批都真的過 rerank（拿到完整 n 的 rerank 訊號）；prod key 或不在意 rerank 就留 0。
    """
    if retriever is None:
        from polaris.retrieval.retriever import active_retriever

        retriever = active_retriever()

    out: list[RetrievalRecord] = []
    for i, it in enumerate(items):
        if pace_seconds and i:
            import time

            time.sleep(pace_seconds)
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
    #: rerank 真的跑過、可比較的題數（rerank_delta 才有意義的分母）。
    n_rerank_ran: int
    rerank_improved: int  # rerank_delta > 0 的題數
    rerank_hurt: int      # rerank_delta < 0 的題數


def summarize(records: list[RetrievalRecord], *, ks: tuple[int, ...] = DEFAULT_KS) -> RetrievalSummary:
    scored = [r for r in records if r.retriever_available and r.answerable == "Y" and r.gold_chunks]
    unavailable = sum(1 for r in records if not r.retriever_available)
    # rerank_delta 只在 rerank 真的跑了（且兩側都命中 → delta 非 None）時才計入。
    reranked = [r for r in scored if r.rerank_ran and r.rerank_delta is not None]

    def _mean(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    return RetrievalSummary(
        n_scored=len(scored),
        n_skipped_unavailable=unavailable,
        hit_post={k: _mean([1.0 if r.hit_post.get(k) else 0.0 for r in scored]) for k in ks},
        recall_pre={k: _mean([r.recall_pre.get(k, 0.0) for r in scored]) for k in ks},
        recall_post={k: _mean([r.recall_post.get(k, 0.0) for r in scored]) for k in ks},
        mrr_post=_mean([r.mrr_post for r in scored]),
        n_rerank_ran=len(reranked),
        rerank_improved=sum(1 for r in reranked if r.rerank_delta > 0),
        rerank_hurt=sum(1 for r in reranked if r.rerank_delta < 0),
    )


__all__ = [
    "DEFAULT_KS",
    "RetrievalRecord",
    "RetrievalSummary",
    "run_retrieval",
    "score_item",
    "summarize",
]
