"""Deep Research 狀態模型（R2 W3 D15；契約見 D11 設計文件）。

純資料 / 純函式：ReActStep（審計步）、dedup_evidence（依 source_id 去重累積）、
should_continue（loop 守門）、DeepResearchResult（最終輸出）。
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict

from polaris.graph.state import Citation

DeepResearchStatus = Literal["running", "answered", "exhausted"]


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
    "should_continue",
    "DeepResearchResult",
    "DeepResearchStatus",
]
