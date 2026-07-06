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


# ── Hermetic credentials（讓整套測試不受環境 ambient 金鑰影響）─────────────────
@pytest.fixture(autouse=True)
def _hermetic_credentials(request, monkeypatch):
    """預設把每個測試釘在「無憑證的確定性路徑」，讓整套測試 hermetic。

    根因（2026-07-05 失敗紀錄的 15 紅燈）：``gemini.available()`` 只看
    ``settings.gemini_api_key`` 有沒有值。CI（無金鑰）→ 走 stub 語料 / DEFAULT_ANCHOR
    → 全綠；但**開發者本機若有真金鑰 / GCP 憑證**，同一批單元 / E2E 測試改走
    real-infra 分支（動態 temporal anchor、真實 BM25 corpus、線上 embedding 檢索），
    於是約 10 個「斷言在 stub / 預設值上」的測試就紅——這正是紀錄裡「到底是我改壞
    還是 main 本來就壞」反覆排查成本的來源。這批紅燈非邏輯回歸，是測試不 hermetic。

    退場機制：
    - ``tests/security/*`` 反而**要**在有金鑰時打真 LLM（``@requires_llm`` 守門、
      收集期就決定 skip 與否），這裡不動它們的金鑰。
    - 想測「有金鑰」路徑的測試自己 ``monkeypatch`` ``settings.gemini_api_key`` /
      ``gemini.available``；那些 patch 在此 fixture 之後套用 → 覆蓋掉這裡的清空。
    """
    from polaris.config import settings
    from polaris.graph import temporal
    from polaris.retrieval import retriever

    # process 級 lru_cache 會跨測試外洩：若某測在有金鑰時填了 2026Q1 / 真實 corpus，
    # 之後無金鑰的測試會讀到快取的髒值。每測前後清乾淨。
    temporal._cached_anchor.cache_clear()
    retriever._cached_real_corpus.cache_clear()

    # security 子樹保留 ambient 金鑰（要打真 LLM 才有意義）。
    if "security" not in Path(str(request.node.fspath)).parts:
        monkeypatch.setattr(settings, "gemini_api_key", "", raising=False)

    yield

    temporal._cached_anchor.cache_clear()
    retriever._cached_real_corpus.cache_clear()
