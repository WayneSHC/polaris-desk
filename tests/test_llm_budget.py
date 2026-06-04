"""LLM token 預算護欄（LLM10）單元測試。"""
from __future__ import annotations

import pytest

from polaris.llm.budget import BudgetExceeded, TokenBudget


def test_no_limit_when_zero():
    b = TokenBudget(0)
    b.charge(10_000_000)
    assert b.used == 10_000_000
    assert b.remaining() == float("inf")


def test_charge_and_remaining():
    b = TokenBudget(100)
    b.charge(30)
    assert b.used == 30
    assert b.remaining() == 70


def test_raises_when_exceeded():
    b = TokenBudget(100)
    b.charge(90)
    with pytest.raises(BudgetExceeded):
        b.charge(20)
    assert b.used == 110          # 用量誠實反映，即使已超限
    assert b.remaining() == 0


def test_negative_charge_clamped():
    b = TokenBudget(100)
    b.charge(-5)
    assert b.used == 0


def test_reset():
    b = TokenBudget(100)
    b.charge(50)
    b.reset()
    assert b.used == 0


def test_default_budget_disabled_by_default():
    """預設 settings.llm_token_budget=0 → 無上限，不改變現有行為。"""
    from polaris.llm.budget import default_budget

    assert default_budget.limit == 0
