"""D8 — POC runner（python -m polaris.compression）。

`build_report` 對代表性語料跑量測並組出可讀報告；CI 走確定性壓縮器，
報告須含關鍵欄位與各語料區段（≥50% 由本機真 LLMLingua 另行回填）。
"""
from __future__ import annotations

from polaris.compression.__main__ import build_report


class TestBuildReport:
    def test_contains_key_fields_and_sections(self):
        report = build_report()
        assert "省幅" in report
        assert "deterministic" in report
        assert "D6 stub 語料" in report

    def test_is_deterministic(self):
        assert build_report() == build_report()
