"""LLM token 預算護欄（LLM10：擋資源耗盡 / 失控成本）。

純整數計帳、零外部依賴、易單測。:class:`GeminiClient` 每次呼叫後把估算的
token 用量記入 process 層的 :data:`default_budget`；累計超過上限即丟
:class:`BudgetExceeded`，擋住後續 LLM 呼叫（保護 $400 預算 + 擋失控迴圈）。

- ``limit <= 0`` → 無上限（**預設**；不改變現有行為，token 紀律仍可靠
  ``settings.llm_max_output_tokens`` 控制每次輸出）。
- 估算用 :func:`polaris.compression.tokens.count_tokens`（呼叫端算好再傳入，
  本模組只記整數）。
"""
from __future__ import annotations

from polaris.config import settings


class BudgetExceeded(RuntimeError):
    """累計 token 超過預算上限。"""


class TokenBudget:
    """process 層 token 計帳器。limit<=0 視為無上限。"""

    def __init__(self, limit: int = 0) -> None:
        self.limit = limit
        self.used = 0

    def charge(self, tokens: int) -> None:
        """記入已用 token（負數視為 0）；累計超過上限則 raise。"""
        self.used += max(0, int(tokens))
        if self.limit > 0 and self.used > self.limit:
            raise BudgetExceeded(
                f"LLM token 預算超限：已用 {self.used} > 上限 {self.limit}"
            )

    def remaining(self) -> float:
        """剩餘額度；無上限回 ``inf``。"""
        if self.limit <= 0:
            return float("inf")
        return float(max(0, self.limit - self.used))

    def reset(self) -> None:
        self.used = 0


#: process 層單例，上限取自 settings.llm_token_budget（預設 0 = 無上限）。
default_budget = TokenBudget(settings.llm_token_budget)


__all__ = ["BudgetExceeded", "TokenBudget", "default_budget"]
