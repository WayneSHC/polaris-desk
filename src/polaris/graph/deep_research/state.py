"""Deep Research 狀態模型（R2 W3 D15；契約見 D11 設計文件）。

純資料 / 純函式：ReActStep（審計步）、dedup_evidence（依 source_id 去重累積）、
should_continue（loop 守門）、DeepResearchResult（最終輸出）。
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict

from polaris.graph.state import Citation

DeepResearchStatus = Literal["running", "answered", "exhausted"]

#: 逐點來源標記：「（來源：<source_id>）」。半/全形括號與冒號皆收
#: （R2：Flash 常輸出半形 `(來源:sid)`，若只認全形冒號 → 閘門永遠 fail → 靜默退回 base）。
_SOURCE_TAG = re.compile(r"[（(]來源[：:]([^）)]+)[）)]")

#: 數字 token：整數 / 小數（含千分位逗號）。
_NUMBER_RE = re.compile(r"\d+(?:[,，]\d{3})*(?:[.．]\d+)?")


class ReActStep(BaseModel):
    """單一 ReAct 步：推理 + 行動 + 觀察（逐步可溯源審計）。"""

    model_config = ConfigDict(frozen=True)

    thought: str
    action: str
    action_input: str = ""
    observation: str = ""


def dedup_evidence(
    existing: Sequence[Citation], new: Sequence[Citation]
) -> list[Citation]:
    """合併兩組引用，依 ``source_id`` 去重、保序（先到先留）。"""
    out: list[Citation] = []
    seen: set[str] = set()
    for cite in [*existing, *new]:
        if cite.source_id in seen:
            continue
        seen.add(cite.source_id)
        out.append(cite)
    return out


def is_fully_traceable(answer: str, evidence: Sequence[Citation]) -> bool:
    """每一條列論點（``- `` 開頭）是否都帶 ``（來源：sid）`` 且 sid ∈ evidence。

    FR-004「句句可溯源」的結構化驗證：至少 1 個論點；header / disclaimer 等
    非條列行豁免；自由文（無 tagged bullet）→ False。
    """
    valid = {c.source_id for c in evidence}
    bullets = [ln for ln in (answer or "").splitlines() if ln.strip().startswith("-")]
    if not bullets:
        return False
    for line in bullets:
        match = _SOURCE_TAG.search(line)
        if not match or match.group(1) not in valid:
            return False
    return True


def is_traceable_prose(text: str, evidence: Sequence[Citation]) -> bool:
    """prose 中是否存在 ≥1 個「（來源：sid）」且 sid ∈ evidence。

    與 :func:`is_fully_traceable`（bullet 格式）不同：此函式適用於自由散文，
    只要至少一個有效引用存在即 pass（P0 Gemini 潤飾後的格式）。
    """
    if not text or not evidence:
        return False
    valid = {c.source_id for c in evidence}
    found_any_valid = any(m.group(1) in valid for m in _SOURCE_TAG.finditer(text))
    return found_any_valid


def _extract_numbers(text: str) -> set[str]:
    """抽出文字中的數字 token（先移除 source-tag 子串，避免 sid 內數字誤算）。"""
    return set(_NUMBER_RE.findall(_SOURCE_TAG.sub("", text)))


def _to_decimal(token: str) -> Decimal | None:
    """把數字 token（含全/半形千分位與小數點）轉成 Decimal；無法解析 → None。"""
    normalized = token.replace(",", "").replace("，", "").replace("．", ".")
    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError):
        return None


def _is_derived_by_add_sub(target: Decimal, base_values: Sequence[Decimal]) -> bool:
    """``target`` 是否恰等於**兩個相異 base 數字**的 ``+`` 或 ``−``（精確相等）。

    #56 Option A：比較敘事天生會算「高出 X 個百分點」這類派生數字。只放行由兩個
    已接地 base 數字經加/減導出、且**重算完全相等**者——我們不信 LLM 的算術，而是
    自己重算後才放行（Flash 算錯即精確不等 → 擋）。不放行乘除、3+ 運算元。
    """
    n = len(base_values)
    for i in range(n):
        for j in range(n):
            if i == j:  # 需兩個相異位置的 base 數字，不得自己湊自己
                continue
            a, b = base_values[i], base_values[j]
            if a + b == target or a - b == target:
                return True
    return False


def numbers_grounded_in_text(
    prose: str, source: str, *, allow_arithmetic: bool = False
) -> bool:
    """``prose`` 中所有數字是否都出現在 ``source`` 文字中（text-vs-text 接地閘門）。

    給「來源就是一段確定性文字」的觸點用（如 peer-compare 的 base 摘要）。
    prose 無數字 → True（無可驗數字）。

    ``allow_arithmetic=True``（#56 Option A）：直接不在 source 的數字，若恰等於
    **兩個相異 base 數字**的 ``+`` / ``−``（精確相等）亦放行；乘除 / 3+ 運算元不放行。
    ⚠️ 殘餘風險：base 內兩不相關數字剛好加/減等於某幻覺數 → 巧合放行（本議題明列之取捨）。
    """
    nums_in_prose = _extract_numbers(prose)
    if not nums_in_prose:
        return True

    source_tokens = _extract_numbers(source)
    if nums_in_prose.issubset(source_tokens):
        return True
    if not allow_arithmetic:
        return False

    base_values = [d for d in (_to_decimal(t) for t in source_tokens) if d is not None]
    for token in nums_in_prose:
        if token in source_tokens:
            continue
        value = _to_decimal(token)
        if value is None or not _is_derived_by_add_sub(value, base_values):
            return False
    return True


def numbers_grounded(text: str, evidence: Sequence[Citation]) -> bool:
    """prose 中所有數字 token 是否都能在 evidence snippets 中找到。

    防幻覺閘門（R2/R3 風險）：
    - 先移除 source-tag 子串再抽數字，避免 sid 內數字（如 stub-2330）誤算。
    - evidence snippet 同樣移 source-tag 後取數字池。
    - prose 無數字 → True（無可驗數字）。
    """
    nums_in_prose = _extract_numbers(text)
    if not nums_in_prose:
        return True

    if not evidence:
        return False

    evidence_pool: set[str] = set()
    for c in evidence:
        evidence_pool.update(_extract_numbers(c.snippet))

    return nums_in_prose.issubset(evidence_pool)


def should_continue(state: Mapping, *, max_loops: int = 6) -> bool:
    """是否續跑 ReAct 迴圈：已 answered 或達 ``max_loops`` 硬上限 → 停（FR-004 ≤6）。"""
    if state.get("status") == "answered":
        return False
    if state.get("iteration", 0) >= max_loops:
        return False
    return True


@dataclass
class DeepResearchResult:
    question: str
    final_answer: str
    evidence: list[Citation] = field(default_factory=list)
    react_steps: list[ReActStep] = field(default_factory=list)
    iterations: int = 0
    status: DeepResearchStatus = "running"
    compliance_status: str = "unknown"


__all__ = [
    "ReActStep",
    "dedup_evidence",
    "is_fully_traceable",
    "is_traceable_prose",
    "numbers_grounded",
    "numbers_grounded_in_text",
    "should_continue",
    "DeepResearchResult",
    "DeepResearchStatus",
]
