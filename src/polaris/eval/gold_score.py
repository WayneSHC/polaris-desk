"""生成-side 確定性檢查 + 失敗分類（gold set 專用）。

兩個 token=0 後檢查（判定系統回答，不呼叫 LLM）：

- **數字正確性**：從回答抽數字，比對 ``exact_number``（eps 兩位小數精確；% 帶容差）。
- **引用-支持（近似）**：系統引用 chunk_id 是否 ∩ ``must_cite_chunk_id``。gold 非窮舉，
  故「off-gold」是**軟訊號**（可能引到另一個同樣有效的塊），標 ``ungrounded?`` 而非硬判。

失敗分類（結合檢索 + 生成，告訴你該修哪一層）：
``ok / retrieval_miss / wrong_number / ungrounded? / over_hedge / unanswerable_ok / answered_uncertain``
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from polaris.eval.gold import GoldItem
from polaris.eval.retrieval import RetrievalRecord

#: 「資料不足」誠實回應標記（對齊 smoke 的 honest_no_data）。
_HEDGE = "資料不足"
#: 數字抽取：整數/小數，容許千分位逗號。
_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


@dataclass
class GenResult:
    """單題生成輸出（供評分；由 run_fn 產出或測試注入）。"""

    answer: str = ""
    citation_ids: tuple[str, ...] = ()
    compliance_status: str = "unknown"


@dataclass
class GoldScore:
    """單題 gold 評分。"""

    item_id: str
    answerable: str
    numeric_ok: bool = False
    grounded: bool = False          # 引用 ∩ gold 非空
    hedged: bool = False            # 回答含「資料不足」
    bucket: str = "ok"              # 失敗分類
    checks: dict[str, bool] = field(default_factory=dict)


def _extract_numbers(text: str) -> list[float]:
    out: list[float] = []
    for tok in _NUM.findall(text or ""):
        try:
            out.append(float(tok.replace(",", "")))
        except ValueError:
            continue
    return out


def numeric_match(answer: str, exact: float | None, unit: str = "") -> bool:
    """回答中是否出現與 ``exact`` 相符的數字。

    - 百分比（unit 含 '%'）：絕對容差 0.1pp。
    - 其餘（如 eps 元/股）：四捨五入至 2 位小數比對（吸收 22.08 vs 22.080 之類）。
    """
    if exact is None:
        return False
    nums = _extract_numbers(answer)
    if "%" in (unit or ""):
        return any(abs(n - exact) <= 0.1 for n in nums)
    return any(round(n, 2) == round(exact, 2) for n in nums)


def score_item(gold: GoldItem, gen: GenResult, retrieval: RetrievalRecord | None) -> GoldScore:
    """結合生成輸出 + 檢索結果 → 評分 + 失敗分類。"""
    hedged = _HEDGE in (gen.answer or "")
    num_ok = numeric_match(gen.answer, gold.exact_number, gold.unit)
    grounded = bool(set(gen.citation_ids) & set(gold.must_cite_chunk_id))
    # 檢索是否撿回 gold（post-rerank 任一 k 命中）。無 retrieval 記錄 → 視為未知(不歸 miss)。
    retrieved = bool(retrieval and any(retrieval.hit_post.values()))

    if gold.answerable != "Y":
        # 語料撐不起 / 待確認：正確行為是誠實說資料不足。
        bucket = "unanswerable_ok" if hedged else "answered_uncertain"
    elif hedged:
        bucket = "over_hedge"           # 撐得起卻退縮
    elif not num_ok:
        # 答錯數字：分是「根本沒撿回」還是「撿回了卻答錯」。
        bucket = "retrieval_miss" if (retrieval and not retrieved) else "wrong_number"
    elif not grounded:
        bucket = "ungrounded?"          # 數字對但引用不在 gold（軟訊號）
    else:
        bucket = "ok"

    return GoldScore(
        item_id=gold.item_id,
        answerable=gold.answerable,
        numeric_ok=num_ok,
        grounded=grounded,
        hedged=hedged,
        bucket=bucket,
        checks={
            "numeric_ok": num_ok,
            "grounded": grounded,
            "not_hedged": not hedged,
        },
    )


def _default_run_fn(item: GoldItem) -> GenResult:
    """預設生成路徑：走 5 節點文字 workflow（scenario 1 財務題）。

    無金鑰 / CI → workflow 走確定性 fallback（stub），仍回得出結構化 GenResult。
    """
    from polaris.eval.runner import _run_workflow

    result = _run_workflow(item.question)
    citations = result.get("citations", []) or []
    cids = tuple(getattr(c, "source_id", "") or "" for c in citations)
    return GenResult(
        answer=result.get("answer", ""),
        citation_ids=tuple(c for c in cids if c),
        compliance_status=result.get("compliance_status", "unknown"),
    )


def run_generation(
    items: list[GoldItem],
    retrieval_by_id: dict[str, RetrievalRecord] | None = None,
    *,
    run_fn=_default_run_fn,
) -> list[GoldScore]:
    """批次生成評測。``retrieval_by_id`` 供失敗分類分辨 retrieval_miss vs wrong_number。"""
    rmap = retrieval_by_id or {}
    return [score_item(it, run_fn(it), rmap.get(it.item_id)) for it in items]


def taxonomy(scores: list[GoldScore]) -> dict[str, list[str]]:
    """失敗分類 → item_id 清單（供報告與定位）。"""
    out: dict[str, list[str]] = {}
    for s in scores:
        out.setdefault(s.bucket, []).append(s.item_id)
    return out


__all__ = [
    "GenResult",
    "GoldScore",
    "numeric_match",
    "run_generation",
    "score_item",
    "taxonomy",
]
