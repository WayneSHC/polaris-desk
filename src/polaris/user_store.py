"""per-user 活動紀錄 + 訂閱清單（Firestore）—— R7-1「使用者活動紀錄」後端。

登入後每次研究 / 同業比較存成一筆 session（B 級：整包 ``result`` 一起存 → 點開
歷史**直接還原**當時答案，不重打 API）；訂閱清單（per-user ``tickers``）與紀錄
共用同一 ``users/{uid}`` doc。

資料模型（見 docs/cross-role-collab/Auth-Firestore_串接指南_R2決議.md §6）::

    users/{uid}                       # uid = Google sub
      ├─ tickers: [...]               # 訂閱清單
      └─ sessions/{sessionId}         # 活動歷史
            origin / query / tickers / created_at / result

設計與 :class:`polaris.structured_store.StructuredStore` 同套：**client 注入式 seam**
——測試注入 fake、CI 0 GCP 外呼；真環境延遲 import ``google.cloud.firestore``
（用 ADC / runtime SA，免金鑰）。**不寫 `polaris_core`**：Firestore 是完全獨立的庫，
天然避開憲法「app 不寫 core」約束。

排序在 Python 端做（按 ``created_at`` 倒序）——避免在查詢路徑 import firestore 常數，
保 CI 不需安裝該套件；per-user 歷史量小，整段取回再排可接受。
"""
from __future__ import annotations

from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _with_id(snap) -> dict:
    return {"id": snap.id, **(snap.to_dict() or {})}


class UserStore:
    """Firestore 的 per-user 紀錄 / 訂閱讀寫層。"""

    def __init__(self, settings, *, client=None) -> None:
        self.settings = settings
        self._client = client  # 注入（測試）或延遲建立（真環境）

    def _get_client(self):
        if self._client is None:
            from google.cloud import firestore  # 延遲 import（重相依不進 CI 必經路徑）
            self._client = firestore.Client(project=self.settings.gcp_project)
        return self._client

    def _user_ref(self, uid: str):
        return self._get_client().collection("users").document(uid)

    def _sessions(self, uid: str):
        return self._user_ref(uid).collection("sessions")

    # ── 活動紀錄（sessions）──────────────────────────────────────────────────

    def save_session(self, uid: str, doc: dict) -> str:
        """存一筆 session（B 級：整包 ``result`` 一起存）→ 回 sessionId。"""
        data = dict(doc)
        data.setdefault("created_at", _now_iso())
        ref = self._sessions(uid).document()  # auto-id
        ref.set(data)
        return ref.id

    def list_sessions(self, uid: str, limit: int = 50) -> list[dict]:
        """該使用者的 session 清單，``created_at`` 倒序，最多 ``limit`` 筆。"""
        items = [_with_id(s) for s in self._sessions(uid).stream()]
        items.sort(key=lambda d: d.get("created_at", ""), reverse=True)
        return items[:limit]

    def get_session(self, uid: str, session_id: str) -> dict | None:
        """單筆 session（含整包 ``result``）供前端完整還原；查無回 None。"""
        snap = self._sessions(uid).document(session_id).get()
        return _with_id(snap) if snap.exists else None

    # ── 訂閱清單（users/{uid}.tickers）────────────────────────────────────────

    def get_subs(self, uid: str) -> list[str]:
        snap = self._user_ref(uid).get()
        return (snap.to_dict() or {}).get("tickers", []) if snap.exists else []

    def set_subs(self, uid: str, tickers: list[str]) -> None:
        """覆蓋訂閱清單（merge=True → 不動 sessions 子集合）。"""
        self._user_ref(uid).set({"tickers": list(tickers)}, merge=True)
