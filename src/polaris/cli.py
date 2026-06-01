"""Polaris Desk CLI — W1 D1 stub mode entry point.

Usage:
    python -m polaris.cli ask "台積電 2025 Q1 營收 YoY"
    python -m polaris.cli ask "..." --stub-buysell    # US2 預留旗標
    python -m polaris.cli ask ""                       # 空輸入守門 demo
"""
from __future__ import annotations

import argparse
import sys
from typing import Any


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="polaris",
        description="Polaris Desk — Multi-Agent Co-Pilot (W1 D1 stub mode)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    ask = sub.add_parser("ask", help="Run the 5-node workflow on a question")
    ask.add_argument("query", help="自然語言問題（W1 D1 唯一輸入）")
    ask.add_argument(
        "--stub-buysell",
        action="store_true",
        help="(US2) make writer emit buy/sell text to demo compliance blocking",
    )

    args = parser.parse_args(argv)

    if args.cmd == "ask":
        return _cmd_ask(args.query, stub_buysell=args.stub_buysell)
    return 1


def _cmd_ask(query: str, *, stub_buysell: bool = False) -> int:
    # 注意：W1 D1 US1 階段 --stub-buysell 只是 reserved flag，
    # 實際攔截行為由 US2 的 compliance.py 接上。
    from polaris.graph.workflow import build_workflow

    app = build_workflow()
    result = app.invoke({"query": query})
    _pretty_print(query, result)
    return 0


def _pretty_print(query: str, result: dict[str, Any]) -> None:
    print("== Polaris Desk (W1 D1 stub mode) ==")
    print(f"Query     : {query!r}")
    print(f"Answer    : {result.get('answer', '<none>')}")
    print(f"Compliance: {result.get('compliance_status', '<none>')}")
    if result.get("halt"):
        print("Halt      : True")

    citations = result.get("citations") or []
    if citations:
        print("Citations :")
        for i, c in enumerate(citations, 1):
            print(f"  [{i}] {c.source_id} — \"{c.snippet}\" (origin={c.origin})")

    trace = result.get("trace") or []
    if trace:
        print("Trace     :")
        for t in trace:
            err = f"  error={t.error_message}" if t.error_message else ""
            print(
                f"  {t.node_name:11s} {t.status:7s} "
                f"{t.elapsed_ms:>4d}ms  "
                f"in={t.input_keys}  out={t.output_keys}{err}"
            )


if __name__ == "__main__":
    sys.exit(main())
