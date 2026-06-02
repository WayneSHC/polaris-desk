"""Polaris Desk — Workflow shared state, citations, and per-node traces.

對應 spec 001-langgraph-skeleton / data-model.md。

- ``Citation``：引用單筆紀錄（pydantic BaseModel）。
- ``NodeTrace``：單次節點執行紀錄（pydantic BaseModel）。
- ``ResearchState``：LangGraph 在 5 節點間傳遞的 TypedDict 狀態。
  - ``trace`` 欄位用 ``Annotated[list[NodeTrace], operator.add]`` reducer，
    讓多個節點 patch 自動 append 而非覆蓋（FR-006 / SC-002 必要條件）。
  - ``total=False`` 允許入口只填 ``query``，其餘欄位由節點漸進填入。
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Citation
# ---------------------------------------------------------------------------

CitationOrigin = Literal["stub", "bm25", "embedding", "colpali", "rerank", "news"]


class Citation(BaseModel):
    """引用單筆紀錄。W1 D1 stub mode 用 origin='stub'；後續週次擴展。"""

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1, description="來源識別（頁碼 hash / URL hash / stub-id）")
    snippet: str = Field(min_length=1, description="被引用的原文片段")
    origin: CitationOrigin = Field(description="檢索來源；W1 固定 'stub'")


# ---------------------------------------------------------------------------
# NodeTrace
# ---------------------------------------------------------------------------

NodeStatus = Literal["ok", "error", "skipped"]


class NodeTrace(BaseModel):
    """單次節點執行紀錄，由 @traced 裝飾器 emit。"""

    model_config = ConfigDict(frozen=True)

    node_name: str = Field(min_length=1)
    status: NodeStatus
    input_keys: list[str] = Field(default_factory=list)
    output_keys: list[str] = Field(default_factory=list)
    error_message: str | None = Field(default=None)
    elapsed_ms: int = Field(ge=0, description="wall-clock 毫秒，不可為負")

    @model_validator(mode="after")
    def _enforce_error_message_consistency(self) -> NodeTrace:
        """status=error 必須有 error_message；status=ok 必須無 error_message。

        skipped 兩種狀態皆允許（通常無，但若上游記了原因也可帶）。
        """
        if self.status == "error" and not (self.error_message and self.error_message.strip()):
            raise ValueError("status='error' requires non-empty error_message")
        if self.status == "ok" and self.error_message is not None:
            raise ValueError("status='ok' must not carry error_message")
        return self


# ---------------------------------------------------------------------------
# PeriodSpec — Temporal Anchoring（W2 D6 / FR-007）
# ---------------------------------------------------------------------------

PeriodKind = Literal["none", "quarter", "fiscal_year", "recent_quarters"]


class PeriodSpec(BaseModel):
    """從問題解析出的期間意圖 + 解析後的具體季別清單。

    - ``hint``：原始時間語句（如「最近兩季」「2024全年」），無則空字串。
    - ``kind``：期間種類。
    - ``quarters``：解析後的季別字串清單（格式 "2024Q3"，對齊 vectorstore），
      供 retriever 以 ``filters={"period": ...}`` 取對應期間資料；none 時為空。
    """

    model_config = ConfigDict(frozen=True)

    hint: str = Field(default="")
    kind: PeriodKind = Field(default="none")
    quarters: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ResearchState — LangGraph TypedDict
# ---------------------------------------------------------------------------

ComplianceStatus = Literal["passed", "blocked", "rewritten", "unknown"]


class ResearchState(TypedDict, total=False):
    """LangGraph state passed between the 5 nodes.

    ``total=False`` 讓入口可以只填 ``query``。每個節點回 patch dict，由 LangGraph
    依欄位 reducer 合併進來。``trace`` 用 ``operator.add`` reducer 確保多節點
    寫入時 append；其他欄位是 last-write-wins。
    """

    # 入口欄位
    query: str

    # 各節點輸出
    plan: list[str]
    period: PeriodSpec
    contexts: list[dict[str, Any]]
    calculations: dict[str, Any]
    draft: str
    answer: str
    citations: list[Citation]
    compliance_status: ComplianceStatus

    # trace 累積（@traced 裝飾器每次回 {"trace": [single_NodeTrace]}）
    trace: Annotated[list[NodeTrace], operator.add]

    # 例外/空輸入時的中斷旗標
    halt: bool


__all__ = [
    "Citation",
    "CitationOrigin",
    "NodeTrace",
    "NodeStatus",
    "PeriodSpec",
    "PeriodKind",
    "ResearchState",
    "ComplianceStatus",
]
