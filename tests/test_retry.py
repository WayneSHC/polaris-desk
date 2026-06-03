"""D7 — 通用 retry primitive（polaris.retry）。

`call_with_retry` 對「可重試」例外做 exponential backoff 重試；分類交給
`is_transient`（暫時性 vs 永久性）。sleep 經 `default_sleep` 間接呼叫，
測試一律注入 no-op / recorder → 快速、確定、無真實等待。
"""
from __future__ import annotations

import pytest

from polaris import retry


class _ApiError(Exception):
    """模擬帶 HTTP 狀態碼的 API 例外（如 google-genai 的 APIError）。"""

    def __init__(self, code: int) -> None:
        super().__init__(f"HTTP {code}")
        self.code = code


# ---------------------------------------------------------------------------
# is_transient — 暫時性 vs 永久性分類
# ---------------------------------------------------------------------------

class TestIsTransient:
    @pytest.mark.parametrize("code", [408, 409, 425, 429, 500, 502, 503, 504])
    def test_transient_status_codes(self, code):
        assert retry.is_transient(_ApiError(code)) is True

    @pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
    def test_permanent_status_codes(self, code):
        assert retry.is_transient(_ApiError(code)) is False

    def test_value_error_is_permanent(self):
        # planner 的 "empty query" 是永久性輸入錯誤，絕不可重試
        assert retry.is_transient(ValueError("empty query")) is False

    def test_timeout_by_type_name(self):
        assert retry.is_transient(TimeoutError("deadline exceeded")) is True

    def test_server_error_by_type_name(self):
        class ServerError(Exception):
            pass

        assert retry.is_transient(ServerError("503-ish")) is True

    def test_plain_runtime_error_not_transient(self):
        assert retry.is_transient(RuntimeError("boom")) is False


# ---------------------------------------------------------------------------
# call_with_retry — 重試迴圈
# ---------------------------------------------------------------------------

class TestCallWithRetry:
    def test_returns_on_first_success(self):
        calls = []

        def fn():
            calls.append(1)
            return "ok"

        assert retry.call_with_retry(fn, sleep=lambda s: None) == "ok"
        assert len(calls) == 1

    def test_no_sleep_on_first_success(self):
        slept = []
        retry.call_with_retry(lambda: "ok", sleep=slept.append)
        assert slept == []

    def test_recovers_after_transient_failures(self):
        attempts = {"n": 0}

        def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise _ApiError(503)
            return "recovered"

        slept = []
        result = retry.call_with_retry(fn, attempts=3, base_delay=0.5, sleep=slept.append)
        assert result == "recovered"
        assert attempts["n"] == 3
        assert slept == [0.5, 1.0]  # exponential backoff between the 3 attempts

    def test_raises_last_after_exhausting_attempts(self):
        def fn():
            raise _ApiError(503)

        with pytest.raises(_ApiError):
            retry.call_with_retry(fn, attempts=3, sleep=lambda s: None)

    def test_permanent_error_not_retried(self):
        calls = []

        def fn():
            calls.append(1)
            raise _ApiError(400)

        with pytest.raises(_ApiError):
            retry.call_with_retry(fn, attempts=3, sleep=lambda s: None)
        assert len(calls) == 1  # 永久性錯誤只呼叫一次

    def test_permanent_error_does_not_sleep(self):
        slept = []

        def fn():
            raise ValueError("permanent")

        with pytest.raises(ValueError):
            retry.call_with_retry(fn, attempts=3, sleep=slept.append)
        assert slept == []

    def test_backoff_capped_at_max_delay(self):
        def fn():
            raise _ApiError(503)

        slept = []
        with pytest.raises(_ApiError):
            retry.call_with_retry(
                fn, attempts=5, base_delay=1.0, max_delay=2.0, sleep=slept.append
            )
        # 1*2^0=1, 1*2^1=2, 1*2^2=4→cap2, 1*2^3=8→cap2 ⇒ 4 個 sleep（5 次嘗試）
        assert slept == [1.0, 2.0, 2.0, 2.0]

    def test_custom_retry_on_predicate_retries_everything(self):
        attempts = {"n": 0}

        def fn():
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise ValueError("retry me")  # 預設不可重試，但 predicate 覆寫
            return "ok"

        result = retry.call_with_retry(
            fn, attempts=2, retry_on=lambda e: True, sleep=lambda s: None
        )
        assert result == "ok"
        assert attempts["n"] == 2

    def test_default_sleep_used_when_sleep_none(self, monkeypatch):
        slept = []
        monkeypatch.setattr(retry, "default_sleep", lambda s: slept.append(s))
        attempts = {"n": 0}

        def fn():
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise _ApiError(503)
            return "ok"

        retry.call_with_retry(fn, attempts=2, base_delay=0.5)  # sleep=None → default_sleep
        assert slept == [0.5]
