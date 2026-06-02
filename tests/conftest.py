"""Shared pytest fixtures & test doubles.

``FakeLLM`` is a deterministic test double for the LLM client contract
(``.generate(prompt, *, flash, system_instruction) -> str``). It lets us
test the **LLM path** of agent nodes without a network call or API key
(TDD + 憲法成本紀律：CI token=0）。
"""
from __future__ import annotations


class FakeLLM:
    """Deterministic stand-in for :class:`polaris.llm.gemini.GeminiClient`.

    Records calls and returns a canned response. No network, no randomness.
    """

    def __init__(self, response: str = "") -> None:
        self.response = response
        self.calls: list[dict] = []

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
        return self.response
