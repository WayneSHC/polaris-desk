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

    sub.add_parser("doctor", help="檢查 .env 內哪些 API 金鑰已正確設定（G1 用）")
    sub.add_parser(
        "bq-smoke", help="BigQuery 雲端管路煙測（G2；不需 R4 入庫資料）"
    )

    args = parser.parse_args(argv)

    if args.cmd == "ask":
        return _cmd_ask(args.query, stub_buysell=args.stub_buysell)
    if args.cmd == "doctor":
        return _cmd_doctor()
    if args.cmd == "bq-smoke":
        return _cmd_bq_smoke()
    return 1


def _cmd_doctor() -> int:
    from polaris.diagnostics import key_status

    print("== Polaris Desk — 金鑰健檢 (doctor) ==")
    statuses = key_status()
    for name, ok in statuses.items():
        print(f"  {name:18s} {'✅ set' if ok else '❌ missing'}")
    if not statuses.get("GEMINI_API_KEY"):
        print("\nGemini 金鑰未設定：節點走確定性 fallback（無 LLM）。")
        print("設定方式見 docs/keys-setup.md。")
    return 0


def _cmd_bq_smoke() -> int:
    from polaris.diagnostics import bigquery_smoke

    print("== Polaris Desk — BigQuery 雲端管路煙測 (bq-smoke) ==")
    report = bigquery_smoke()
    icons = {"ok": "✅", "skipped": "⏭️", "pending": "⏳", "fail": "❌"}
    for st in report.steps:
        print(f"  {st.name:13s} {icons.get(st.status, '?')} {st.status:8s} {st.detail}")
    print(f"\n  overall: {report.overall}")
    # pending / skipped 是 pre-R4 / pre-creds 的預期狀態，非失敗 → 退出碼 0。
    return 1 if report.overall == "fail" else 0


def _cmd_ask(query: str, *, stub_buysell: bool = False) -> int:
    if stub_buysell:
        # US2 demo：把 writer 模組屬性換成會回「建議買進」的版本。
        # 這跟測試用 monkeypatch.setattr(stubs, "writer", ...) 是對稱的做法。
        # CLI 跑完即退出，全域狀態變更不外溢。
        from polaris.graph.nodes import stubs
        stubs.writer = stubs.writer_with_buysell  # type: ignore[assignment]

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
