"""Cloud Run 健康檢查骨架 server（W4 上雲 prep / D20–22 前置）。

目的：讓容器能在 Cloud Run **真正啟動並通過健康探針** —— 證明套件 import 得起來、
``settings`` 載入正常。**刻意不含產品 ``/ask`` 端點**（那是之後的 API 任務）。

零外部相依：用標準函式庫 ``http.server``，不引入 FastAPI / uvicorn，貼合
「只做部署機制、不動 API」的範圍。

跑法：``python -m polaris.server``（監聽 ``$PORT``，Cloud Run 會注入；本地預設 8000）。
"""
from __future__ import annotations

import json
import os
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, HTTPServer

from polaris.config import settings

#: Cloud Run 未注入 $PORT 時（本地）用的預設埠
DEFAULT_PORT = 8000


def resolve_port(env: Mapping[str, str] | None = None) -> int:
    """解析監聽埠：Cloud Run 注入 ``$PORT``；缺省 / 壞值退 :data:`DEFAULT_PORT`。

    壞值（非數字）也退回預設、**永不 raise** —— 容器絕不能因環境變數髒了就啟動失敗。
    """
    raw = (os.environ if env is None else env).get("PORT", "")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return DEFAULT_PORT


def health_payload() -> dict[str, str]:
    """健康檢查內容：證明 import OK + 設定載入。**不含任何祕密。**"""
    return {
        "status": "ok",
        "service": "polaris-desk",
        "app_env": settings.app_env,
        "vector_backend": settings.vector_backend,
    }


class _HealthHandler(BaseHTTPRequestHandler):
    """只回 /healthz（+ /）的最小 handler；其餘路徑 404。"""

    def _send(self, code: int, body: dict) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 — stdlib 介面固定大小寫
        if self.path in ("/healthz", "/health"):
            self._send(200, health_payload())
        elif self.path == "/":
            self._send(200, {"status": "ok", "hint": "GET /healthz；/ask 為之後的 API 任務"})
        else:
            self._send(404, {"error": "not found", "path": self.path})

    def log_message(self, *_args) -> None:  # 靜音預設 stderr 存取日誌（避免測試噪音）
        return


def build_server(port: int | None = None) -> HTTPServer:
    """建立（未啟動的）HTTP server；``port=0`` 取臨時埠（測試用）。"""
    resolved = resolve_port() if port is None else port
    return HTTPServer(("0.0.0.0", resolved), _HealthHandler)  # noqa: S104 — 容器內需綁全介面


def main() -> None:  # pragma: no cover - 進入點，由 `python -m polaris.server` 啟動
    server = build_server()
    host, port = server.server_address[:2]
    print(f"Polaris Desk health server on {host}:{port} — GET /healthz（/ask 待後續 API 任務）")
    server.serve_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
