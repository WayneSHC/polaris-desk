"""Shared pytest fixtures & test doubles.

``FakeLLM`` is a deterministic test double for the LLM client contract
(``.generate(prompt, *, flash, system_instruction) -> str``). It lets us
test the **LLM path** of agent nodes without a network call or API key
(TDD + 憲法成本紀律：CI token=0）。

D7 retry：``FakeLLM`` 可設定 ``fail_times`` / ``error`` 模擬暫時性 / 永久性失敗；
``ApiError`` 是帶 HTTP 狀態碼的假例外；``no_retry_sleep`` fixture 把 retry 的
退避等待換成 no-op，讓會觸發重試的測試不真的等待。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from polaris import retry


class ApiError(Exception):
    """模擬帶 HTTP 狀態碼的 API 例外（如 google-genai 的 APIError）。

    ``code`` 由 :func:`polaris.retry.is_transient` 用來分類暫時性 / 永久性。
    """

    def __init__(self, code: int) -> None:
        super().__init__(f"HTTP {code}")
        self.code = code


class FakeLLM:
    """Deterministic stand-in for :class:`polaris.llm.gemini.GeminiClient`.

    Records calls and returns a canned response. No network, no randomness.

    - ``fail_times``：前 N 次 ``generate`` 先丟 ``error``（預設 transient 的
      ``ApiError(503)``），用來測試 retry / fallback 行為。
    - ``error``：要丟的例外實例（``None`` → ``ApiError(503)``）。
    """

    def __init__(
        self,
        response: str = "",
        *,
        fail_times: int = 0,
        error: BaseException | None = None,
    ) -> None:
        self.response = response
        self.calls: list[dict] = []
        self._fail_times = fail_times
        self._error = error if error is not None else ApiError(503)

    def generate(
        self,
        prompt: str,
        *,
        flash: bool = False,
        system_instruction: str | None = None,
    ) -> str:
        self.calls.append(
            {"prompt": prompt, "flash": flash, "system_instruction": system_instruction}
        )
        if self._fail_times > 0:
            self._fail_times -= 1
            raise self._error
        return self.response


@pytest.fixture
def no_retry_sleep(monkeypatch):
    """把 retry 退避等待換成 no-op —— 會觸發重試的測試用它避免真的 sleep。"""
    monkeypatch.setattr(retry, "default_sleep", lambda _s: None)


# ── fetch-tw-earnings-call skill path wiring ─────────────────────────────────
# 讓 tests 能 import skill 的 stdlib-only 模組（不進 polaris 套件、保持可攜）。
_SKILL_SCRIPTS = (
    Path(__file__).resolve().parent.parent
    / ".claude" / "skills" / "fetch-tw-earnings-call" / "scripts"
)
if str(_SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS))
