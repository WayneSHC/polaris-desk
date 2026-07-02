#!/usr/bin/env python
"""L2 範圍 gate 的 with-key false-block 驗證（INPUT_GATE_SCOPE 上線前跑）。

回歸測試 tests/test_input_gate_eval.py 是 **token-free** 的——只證明確定性 floor 不誤擋、
覆蓋率夠；但沒實際跑過 Gemini 分類器。本腳本補上那一段：對 eval 金標集（142 題**正當**
投研題）跑完整 :func:`polaris.graph.input_gate.screen`（含 LLM smart 層），量真正的
**false-block 率**（in-scope 題被判 off_topic / injection 而擋掉的比例）。

用法（需有金鑰，否則 LLM 層不啟用、退回 floor-only）：
    GEMINI_API_KEY=<key> python scripts/scope_gate_check.py [題庫.csv]

判讀：
- false-block 率應接近 0%。偏高 → 看被擋清單，擴 input_gate._SCOPE_KEYWORDS（floor 正向
  放行）或調 prompts.SCOPE_SYSTEM_PROMPT，別直接放寬到讓離題也過。
- 退出碼：0 = 通過門檻（預設 ≤2%）；1 = 超標，勿開 INPUT_GATE_SCOPE。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 允許直接 `python scripts/scope_gate_check.py`（把 src/ 加進 path）。
_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from polaris.eval.dataset import load_dataset  # noqa: E402
from polaris.graph.input_gate import screen  # noqa: E402
from polaris.llm.gemini import active_llm, available  # noqa: E402

#: false-block 率上限（超過即退出碼 1、勿開 flag）。實測 floor 覆蓋率 97.2%、殘餘走 LLM。
FALSE_BLOCK_CEILING = 0.02

_DEFAULT_DATASET = _SRC / "polaris" / "eval" / "data" / "questions_v1.csv"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    dataset = Path(args[0]) if args else _DEFAULT_DATASET

    if not available():
        print(
            "⚠️  無 GEMINI_API_KEY → LLM smart 層不啟用，只會驗到 floor。"
            "請帶金鑰重跑才有意義：GEMINI_API_KEY=<key> python scripts/scope_gate_check.py",
            file=sys.stderr,
        )

    items = load_dataset(dataset)
    client = active_llm()

    blocked: list[tuple[str, str]] = []  # (reason, question)
    for it in items:
        # 金標集全為 in-scope 正當題 → 任何 blocked 都是 false-block。
        decision = screen(it.question, client)
        if not decision.allowed:
            blocked.append((decision.reason, it.question))

    n = len(items)
    rate = len(blocked) / n if n else 0.0
    print(f"題庫：{dataset}")
    print(f"總題數：{n} | LLM 層：{'啟用' if client else '關閉（floor-only）'}")
    print(f"false-block：{len(blocked)}（{rate:.1%}）| 門檻 ≤{FALSE_BLOCK_CEILING:.0%}")
    for reason, q in blocked:
        print(f"  ✗ [{reason}] {q[:70]}")

    if rate > FALSE_BLOCK_CEILING:
        print("\n❌ 超過門檻——勿開 INPUT_GATE_SCOPE，先擴關鍵字集 / 調 SCOPE_SYSTEM_PROMPT。")
        return 1
    print("\n✅ 通過門檻——可開 INPUT_GATE_SCOPE。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
