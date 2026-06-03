"""Compliance Agent（R2 W2 D9）— 6 關鍵字確定性 floor + Gemini smart 層。

把 Compliance 從純 substring 黑名單畢業成 Agent（鏡像 planner_agent / writer_agent）。
防禦採 **defense-in-depth、fail-to-floor**：

- **Layer 1（floor）**：:func:`polaris.graph.compliance.apply_compliance` 的 6 關鍵字
  確定性攔截，**永遠先跑、命中即收、LLM 永不解除**（lexicon 擴充是 R6 的事）。
- **Layer 2（smart）**：有金鑰時用 Gemini Flash 分類器，補抓關鍵字之外的**隱性建議**
  （進場時機 / 逢低布局 / 值得擁有…）。LLM **只回 verdict、永不改寫** draft → 零
  prompt-injection；攔截輸出恆為 ``SAFE_MESSAGE``（SC-003 不破）。
- **fail-to-floor**：LLM 任何失敗（用 D7 retry 撐過暫時性後仍失敗）→ 退回 floor 結果，
  絕不弱化既有保證；Gemini 掛掉也不比今天的 keyword-only 差。
"""
from __future__ import annotations

from typing import Protocol

from polaris.graph.compliance import ComplianceStatus, SAFE_MESSAGE, apply_compliance
from polaris.retry import call_with_retry


class _LLM(Protocol):
    def generate(
        self, prompt: str, *, flash: bool = ..., system_instruction: str | None = ...
    ) -> str: ...


COMPLIANCE_SYSTEM_PROMPT = (
    "你是台灣證券法遵審查者。判斷文字是否包含任何投資買賣建議——"
    "包含顯性（建議買進 / 賣出、加減碼、看多看空）與隱性 / 誘導性語句"
    "（如「現在很適合進場」「逢低布局」「值得擁有」「可以期待」）。"
    "只輸出一個詞：VIOLATION（有買賣建議）或 CLEAN（無），不要解釋。"
)


def _build_prompt(draft: str) -> str:
    return (
        "請審查以下文字是否包含任何投資買賣建議（含隱性 / 誘導性語句）。\n"
        "只回一個詞：VIOLATION 或 CLEAN。\n\n"
        f"待審文字：\n{draft}"
    )


def _is_violation(verdict: str | None) -> bool:
    """解析 LLM verdict。token-first；空 / 模糊 → False（保守，floor 仍守關鍵字）。"""
    stripped = (verdict or "").strip()
    if not stripped:
        return False
    upper = stripped.upper()
    if upper.startswith("CLEAN") or stripped.startswith("合規"):
        return False
    return upper.startswith("VIOLATION") or stripped.startswith("違規")


def llm_flags_violation(draft: str, client: _LLM) -> bool:
    """用 Gemini Flash 判斷 draft 是否含（含隱性）買賣建議。"""
    verdict = client.generate(
        _build_prompt(draft), flash=True, system_instruction=COMPLIANCE_SYSTEM_PROMPT
    )
    return _is_violation(verdict)


def review(draft: str, client: _LLM | None) -> tuple[str, ComplianceStatus]:
    """Compliance Agent 主流程。回 (answer, status)，契約同 apply_compliance。

    - Layer 1 floor 命中 → 直接回（LLM 不被諮詢、永不解除）。
    - Layer 2：有金鑰且 draft 有內容 → Gemini 分類；flagged → 攔成 SAFE_MESSAGE。
    - LLM 失敗 → fail-to-floor（退回 floor 的 passed，不崩、不弱化保證）。
    """
    answer, status = apply_compliance(draft)
    if status == "blocked":
        return answer, status
    if client is not None and draft.strip():
        try:
            flagged = call_with_retry(lambda: llm_flags_violation(draft, client))
        except Exception:  # noqa: BLE001 — LLM 任何失敗都 fail-to-floor
            flagged = False
        if flagged:
            return SAFE_MESSAGE, "blocked"
    return draft, "passed"


__all__ = [
    "COMPLIANCE_SYSTEM_PROMPT",
    "llm_flags_violation",
    "review",
]
