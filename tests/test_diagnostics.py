"""D5 — 金鑰健檢（doctor / make check-keys 的核心邏輯）。"""
from __future__ import annotations

from polaris import diagnostics


class TestKeyStatus:
    def test_reports_all_known_providers(self):
        status = diagnostics.key_status()
        for name in (
            "GEMINI_API_KEY",
            "COHERE_API_KEY",
            "TAVILY_API_KEY",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
        ):
            assert name in status
            assert isinstance(status[name], bool)

    def test_placeholder_key_reported_missing(self, monkeypatch):
        from polaris.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "# 必填")
        assert diagnostics.key_status()["GEMINI_API_KEY"] is False

    def test_real_key_reported_set(self, monkeypatch):
        from polaris.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "AIzaReal999")
        assert diagnostics.key_status()["GEMINI_API_KEY"] is True


class TestDoctorCLI:
    def test_doctor_returns_0_and_lists_gemini(self, capsys):
        from polaris.cli import main

        rc = main(["doctor"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "GEMINI_API_KEY" in out
        assert ("set" in out) or ("missing" in out)
