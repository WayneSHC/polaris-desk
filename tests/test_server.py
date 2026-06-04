"""polaris.server — Cloud Run 健康檢查骨架（W4 上雲 prep / D20–22 前置）。

只證明容器能 import 套件、設定能載入、健康探針通過；**刻意不含產品 /ask**
（那是之後的 API 任務）。token-free：完全不碰 Gemini / 外部金鑰。
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from polaris import server


class TestResolvePort:
    def test_defaults_to_8000_when_unset(self):
        assert server.resolve_port({}) == 8000

    def test_reads_PORT_env(self):
        # Cloud Run 以 $PORT 注入監聽埠
        assert server.resolve_port({"PORT": "8080"}) == 8080

    def test_non_numeric_falls_back(self):
        # 壞值不得讓容器啟動失敗 → 退預設、永不 raise
        assert server.resolve_port({"PORT": "not-a-number"}) == server.DEFAULT_PORT


class TestHealthPayload:
    def test_status_ok_and_reports_config(self):
        payload = server.health_payload()
        assert payload["status"] == "ok"
        assert "app_env" in payload
        assert "vector_backend" in payload

    def test_payload_leaks_no_secrets(self):
        # 健康檢查內容不得含任何金鑰（祕密只在 Secret Manager / 執行期環境）
        blob = json.dumps(server.health_payload()).lower()
        for leak in ("api_key", "secret", "password", "token"):
            assert leak not in blob


@pytest.fixture
def live_server():
    srv = server.build_server(port=0)  # port=0 → 取臨時埠，測試彼此不衝突
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    _host, port = srv.server_address[:2]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=2)


def _get(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=3) as resp:  # noqa: S310 (本地測試固定 http)
        return resp.status, resp.read().decode()


class TestHealthServer:
    def test_healthz_returns_200_ok(self, live_server):
        status, body = _get(f"{live_server}/healthz")
        assert status == 200
        assert json.loads(body)["status"] == "ok"

    def test_root_returns_200(self, live_server):
        status, _ = _get(f"{live_server}/")
        assert status == 200

    def test_unknown_path_returns_404(self, live_server):
        with pytest.raises(urllib.error.HTTPError) as exc:
            _get(f"{live_server}/definitely-not-a-route")
        assert exc.value.code == 404
