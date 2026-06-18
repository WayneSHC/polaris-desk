"""polaris.auth — Google OAuth id_token 驗證（可選 dependency）。

無 token → 匿名（回 None）→ 保 token-free CI 與斷網 / Google 不可達降級（憲法 V）。
有合法 Bearer → 回 Google claims（含 sub）。驗證細節（JWKS / aud）延遲 import，
不進 CI 必經路徑；本測試把 verify_token monkeypatch 掉，0 外呼、0 金鑰。
"""
from __future__ import annotations

from polaris import auth


class TestCurrentUser:
    def test_no_authorization_header_is_anonymous(self):
        assert auth.current_user(None) is None

    def test_non_bearer_scheme_is_anonymous(self):
        assert auth.current_user("Basic Zm9vOmJhcg==") is None

    def test_valid_bearer_returns_claims(self, monkeypatch):
        monkeypatch.setattr(
            auth, "verify_token", lambda t: {"sub": "u-123", "email": "a@b.c"}
        )
        user = auth.current_user("Bearer good.jwt.token")
        assert user is not None
        assert user["sub"] == "u-123"

    def test_invalid_bearer_is_anonymous(self, monkeypatch):
        monkeypatch.setattr(auth, "verify_token", lambda t: None)
        assert auth.current_user("Bearer bad.token") is None

    def test_bearer_token_is_passed_to_verifier(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(auth, "verify_token", lambda t: seen.setdefault("tok", t))
        auth.current_user("Bearer abc.def.ghi")
        assert seen["tok"] == "abc.def.ghi"
