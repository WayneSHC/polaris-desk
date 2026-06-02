"""D4 — CLI 端到端 + 進入點。

驗證兩個文件化指令都能跑：
    python -m polaris.cli ask "..."
    python -m polaris ask "..."        # 需要 src/polaris/__main__.py

子程序測試用 PYTHONPATH=src（與 pyproject 的 pytest pythonpath 一致），
不依賴是否已 editable-install，純測進入點 wiring。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SRC = str(Path(__file__).parent.parent / "src")


def _run_module(module: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": SRC, "PATH": "/usr/bin:/bin"},
    )


class TestCLIMainFunction:
    def test_ask_returns_0_and_prints_answer(self, capsys):
        from polaris.cli import main

        rc = main(["ask", "台積電 2025 Q1 營收 YoY"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Answer" in out
        assert "Trace" in out

    def test_empty_query_prints_halt_message(self, capsys):
        from polaris.cli import main

        rc = main(["ask", ""])
        out = capsys.readouterr().out
        assert rc == 0
        assert "請提供具體問題。" in out


class TestModuleEntrypoints:
    def test_python_m_polaris_cli(self):
        proc = _run_module("polaris.cli", "ask", "台積電 Q1")
        assert proc.returncode == 0, proc.stderr
        assert "Answer" in proc.stdout

    def test_python_m_polaris(self):
        """需要 src/polaris/__main__.py 才會通過。"""
        proc = _run_module("polaris", "ask", "台積電 Q1")
        assert proc.returncode == 0, proc.stderr
        assert "Answer" in proc.stdout
