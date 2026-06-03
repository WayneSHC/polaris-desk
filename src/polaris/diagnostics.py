"""金鑰健檢（R2 W1 D5）— 報告 .env 內哪些 API 金鑰真的設定了。

供 `python -m polaris doctor` / `make check-keys` 使用，讓全隊在 G1 前能一眼
確認「GCP·Gemini key 全隊可用」這個閘門項目。判斷沿用
:func:`polaris.llm.gemini.is_real_key`（空 / 空白 / `#` 開頭一律視為未設定）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from polaris.config import settings
from polaris.llm.gemini import is_real_key

#: 對外顯示名稱 → Settings 屬性名。
KEY_FIELDS: dict[str, str] = {
    "GEMINI_API_KEY": "gemini_api_key",
    "COHERE_API_KEY": "cohere_api_key",
    "TAVILY_API_KEY": "tavily_api_key",
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "OPENAI_API_KEY": "openai_api_key",
}


def key_status() -> dict[str, bool]:
    """回傳 {顯示名稱: 是否已設定真值}。"""
    return {
        name: is_real_key(getattr(settings, attr, ""))
        for name, attr in KEY_FIELDS.items()
    }


# ---------------------------------------------------------------------------
# BigQuery 雲端管路煙測（R2 W2 D10）— 驗證上雲管路，不需 R4 入庫資料。
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SmokeStep:
    """單一煙測步驟結果。status ∈ {ok, skipped, pending, fail}。"""

    name: str
    status: str
    detail: str


#: overall 取最差：fail > pending > skipped > ok。
_OVERALL_RANK = {"ok": 0, "skipped": 1, "pending": 2, "fail": 3}


@dataclass(frozen=True)
class SmokeReport:
    steps: list[SmokeStep]

    @property
    def overall(self) -> str:
        if not self.steps:
            return "ok"
        worst = max(_OVERALL_RANK.get(s.status, 0) for s in self.steps)
        return next(k for k, v in _OVERALL_RANK.items() if v == worst)


def _gcp_creds_available() -> bool:
    """是否偵測到 GCP ADC 金鑰（確定性；CI 未設 → False → 連線步驟 skipped）。"""
    return bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip())


def bigquery_smoke(settings=None, *, store=None, creds_available=None) -> SmokeReport:
    """BigQuery 上雲管路煙測（不需 R4 入庫資料）。

    - **config**（離線、必跑）：報 backend / project / dataset；project 缺 → fail。
    - **connectivity**（creds-gated）：``BigQueryStore.health_check()`` →
      True=ok、``NotImplementedError``=pending（待 R4，管路就緒）、其他例外/False=fail；
      無金鑰 → skipped。

    ``store`` / ``creds_available`` 可注入 → 離線確定性可測。
    """
    from polaris.config import settings as _default

    s = settings if settings is not None else _default
    steps: list[SmokeStep] = []

    project = (getattr(s, "gcp_project", "") or "").strip()
    dataset = getattr(s, "bq_dataset", "") or ""
    backend = getattr(s, "vector_backend", "")
    if not project:
        steps.append(SmokeStep("config", "fail", "gcp_project 未設定（無法連 BigQuery）"))
    else:
        steps.append(
            SmokeStep("config", "ok", f"backend={backend} project={project} dataset={dataset}")
        )

    creds = _gcp_creds_available() if creds_available is None else creds_available
    if not creds:
        steps.append(
            SmokeStep(
                "connectivity",
                "skipped",
                "無 GCP 金鑰：設 GOOGLE_APPLICATION_CREDENTIALS 或 "
                "gcloud auth application-default login 後重跑",
            )
        )
    else:
        bq = store
        if bq is None:
            from polaris.vectorstore.bigquery_store import BigQueryStore

            bq = BigQueryStore(s)
        try:
            ok = bq.health_check()
            steps.append(
                SmokeStep(
                    "connectivity",
                    "ok" if ok else "fail",
                    "health_check 回 True" if ok else "health_check 回 False",
                )
            )
        except NotImplementedError:
            steps.append(
                SmokeStep(
                    "connectivity",
                    "pending",
                    "BigQueryStore.health_check 待 R4 實作（管路就緒，補完即自動轉真）",
                )
            )
        except Exception as exc:  # noqa: BLE001 — 連線/權限任何錯都報 fail
            steps.append(
                SmokeStep("connectivity", "fail", f"連線失敗：{type(exc).__name__}: {exc}")
            )

    return SmokeReport(steps=steps)


__all__ = [
    "key_status",
    "KEY_FIELDS",
    "SmokeStep",
    "SmokeReport",
    "bigquery_smoke",
]
