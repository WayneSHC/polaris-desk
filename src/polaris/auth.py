"""Google OAuth id_token 驗證 —— 後端 app 層身分（R7-1 決議）。

**可選**：無 / 非法 token → 回 ``None``（匿名）。這條路是降級保命——保住
token-free CI 與斷網 / Google 不可達時的備援（憲法 V），**不是預設體驗**；
測試 + Demo 走登入版（前端帶 ``Authorization: Bearer <Google id_token>``）。

驗證重相依（``google-auth`` 的 JWKS 取用）**延遲 import**，不進 CI 必經路徑；
單元測試把 :func:`verify_token` monkeypatch 掉即可 0 外呼、0 金鑰。

設計要點（見 docs/cross-role-collab/Auth-Firestore_串接指南_R2決議.md）：
- 認 **Google** 簽發的 id_token，``aud`` = ``settings.google_client_id``。
- 使用者主鍵取 claims 的 ``sub``（穩定、唯一；**不要用 email**，email 會變）。
"""
from __future__ import annotations

from fastapi import Header

from polaris.config import settings

_BEARER = "Bearer "


def verify_token(token: str) -> dict | None:
    """驗 Google id_token → 回 claims（含 ``sub`` / ``email`` / ``name``）；失敗回 None。

    驗簽 + ``exp`` + ``iss`` + ``aud`` 全交給 ``google-auth``。任何例外（過期 / 簽章
    錯 / aud 不符 / 套件未安裝）一律當匿名處理，絕不讓 auth 錯誤拖垮請求。
    """
    try:
        from google.auth.transport import requests as ga_requests
        from google.oauth2 import id_token

        return id_token.verify_oauth2_token(
            token, ga_requests.Request(), settings.google_client_id
        )
    except Exception:
        return None


def current_user(authorization: str | None = Header(default=None)) -> dict | None:
    """FastAPI 可選 dependency：回 Google claims，或 None（匿名）。"""
    if not authorization or not authorization.startswith(_BEARER):
        return None
    return verify_token(authorization[len(_BEARER):])
