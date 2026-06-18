# 給 R7 的串接指南 — Google OAuth + Firestore（使用者活動紀錄）

> **誰看**：R7（前端）＋ R2/R3（後端）。**對應決策**：[`2_需求清單_from_R7.md`](./2_需求清單_from_R7.md) R7-1。
> **目標**：登入用 **Google OAuth**（NextAuth），登入後把每次研究 / 同業比較存成
> **可完整還原的歷史 session**（B 級，類似 Claude Code 左欄），存進 **Firestore**。
> **時程**：登入版在**測試期就接起來、Demo 當天用登入版展示**（含個人歷史）。
> **不變量**：無 token → 匿名照跑（**僅** token-free CI 與斷網 / Google 不可達時的降級，非預設）；不寫 `polaris_core`；金鑰進 Secret Manager。

---

## 0. 全貌（一張圖）

```
[使用者]
   │ 1. 點 Google 登入
   ▼
[Vercel 前端 / NextAuth]  ──2. 拿到 Google id_token（JWT）──┐
   │                                                        │
   │ 3. 呼叫後端時帶 Authorization: Bearer <id_token>        │
   ▼                                                        │
[Cloud Run /research /peer-compare /history /subscriptions]  │
   │ 4. 驗 id_token（Google JWKS, aud=client_id）→ 取 sub     │
   │ 5. 讀寫 Firestore（按 sub 隔離）                         │
   ▼                                                        │
[Firestore]  users/{sub}/sessions/*  +  users/{sub} (訂閱)  ◀┘
```

**身分傳遞採「直送 Google id_token」**：前端不另簽 token、後端只認 Google，前後端零共享密鑰，最簡單。

---

## 1. 分工（誰做什麼）

| 步驟 | 負責 | 內容 |
|---|---|---|
| 建 Google OAuth Client | **R2 / PM** | GCP Console → OAuth 2.0 Client（Web）→ 給 R7 `CLIENT_ID` / `CLIENT_SECRET` |
| 設 redirect / origin | **R2 + R7** | 授權 redirect：`https://<vercel-domain>/api/auth/callback/google`；JS origin：`https://<vercel-domain>` |
| NextAuth + 登入 UI | **R7** | `[...nextauth]/route.ts`、`signIn/signOut`、AppShell 顯示真實使用者 |
| 呼叫後端帶 Bearer | **R7** | api client 附 `Authorization` header |
| 後端 JWT 驗證 | **R2 / R3** | FastAPI 可選 dependency（無 token = 匿名） |
| Firestore store + 端點 | **R2 / R3** | `/history`(POST/GET/GET{id})、`/subscriptions`(GET/POST) |
| CORS + SA 權限 | **R2** | Cloud Run 加 Vercel 網域；runtime SA 加 `roles/datastore.user` |

---

## 2. 環境變數 / 金鑰對照

| 變數 | 放哪 | 用途 |
|---|---|---|
| `GOOGLE_CLIENT_ID` | **Vercel**（前端）＋ **Cloud Run**（後端驗 `aud`） | OAuth client id |
| `GOOGLE_CLIENT_SECRET` | **Vercel** only（NextAuth 換 code 用） | 後端**不需要** |
| `NEXTAUTH_SECRET` | **Vercel**（建議 Secret Manager → 注入） | NextAuth session 簽章；`openssl rand -base64 32` |
| `NEXTAUTH_URL` | **Vercel** | 部署網址，如 `https://polaris-desk.vercel.app` |
| `NEXT_PUBLIC_API_BASE` | **Vercel** | 後端 URL：`https://polaris-api-14326813937.asia-east1.run.app` |
| （Firestore 認證） | **Cloud Run SA** | 用 ADC，**不需金鑰**；SA 加 `roles/datastore.user` |

> 後端只多吃一個 `GOOGLE_CLIENT_ID`（驗 aud）；client secret 永遠不進後端。

---

## 3. 前端（R7）

### 3-1. NextAuth route（App Router, next-auth v4）
`src/app/api/auth/[...nextauth]/route.ts`
```ts
import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

const handler = NextAuth({
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  ],
  callbacks: {
    // 把 Google 的 id_token 收進 session，供後端驗證用
    async jwt({ token, account }) {
      if (account?.id_token) token.idToken = account.id_token;
      return token;
    },
    async session({ session, token }) {
      (session as any).idToken = token.idToken;
      return session;
    },
  },
});

export { handler as GET, handler as POST };
```
> next-auth v5 (Auth.js) 改用 `auth()` handler，概念相同；jwt/session callback 一樣把 `account.id_token` 存進去。

### 3-2. 登入 / 登出 / 顯示使用者
```ts
import { signIn, signOut, useSession } from "next-auth/react";

// 設定頁 Google 按鈕（取代目前無作用的按鈕）
<button onClick={() => signIn("google")}>使用 Google 登入</button>
<button onClick={() => signOut()}>登出</button>

// AppShell 取代 hardcoded "Jing Chen"
const { data: session } = useSession();
session?.user?.name; session?.user?.image;
```

### 3-3. 呼叫後端時帶 token（核心）
```ts
import { getSession } from "next-auth/react";

async function authHeaders() {
  const session = await getSession();
  const t = (session as any)?.idToken;
  return t ? { Authorization: `Bearer ${t}` } : {}; // 無登入 → 不帶 → 後端視為匿名
}

// 例：研究
const res = await fetch(`${API}/research`, {
  method: "POST",
  headers: { "Content-Type": "application/json", ...(await authHeaders()) },
  body: JSON.stringify({ question }),
});
const result = await res.json();
```

### 3-4. 存歷史（B 級：把整包 result 一起送）
研究 / 同業比較拿到結果後，**多打一次** `POST /history`：
```ts
await fetch(`${API}/history`, {
  method: "POST",
  headers: { "Content-Type": "application/json", ...(await authHeaders()) },
  body: JSON.stringify({
    origin: "research",          // "research" | "peer"
    query,
    tickers,                     // string[]
    result,                      // ← B 級：整包 /research 回應，供日後完整還原
  }),
});
```
> 若 R2/R3 採「workflow 結尾自動寫入」，前端就**省略這步**（後端會說明）。

### 3-5. /history 頁（B 級還原，取代 localStorage）
```ts
// 列表
const list = await fetch(`${API}/history`, { headers: await authHeaders() }).then(r => r.json());
// 點開某筆 → 直接還原當時答案，不重打 /research
const full = await fetch(`${API}/history/${id}`, { headers: await authHeaders() }).then(r => r.json());
renderResult(full.result);   // full.result 就是當初存的整包
```

### 3-6. 匿名 / 斷網降級（fallback，非預設）
- 預設體驗是**登入版**（測試 + Demo 都用它）。
- 但若 `getSession()` 無（未登入 / Google 不可達 / 斷網）→ 不帶 Authorization → 後端回匿名、不寫 Firestore，/history 退回 **localStorage MVP**。
- 這條路只是**降級保命**（保 token-free CI 與斷網備援，憲法 V），不是給 Demo 用的主路徑。

---

## 4. 後端（R2 / R3）

### 4-1. 依賴
```
google-cloud-firestore
google-auth        # 多半已隨其他 google 套件進來；缺再補
```

### 4-2. Google id_token 驗證（可選 dependency）
`src/polaris/auth.py`（新）
```python
from fastapi import Header
from google.oauth2 import id_token
from google.auth.transport import requests as ga_requests
from polaris.config import settings

_req = ga_requests.Request()

def _verify(token: str) -> dict | None:
    try:
        # 驗簽 + exp + iss + aud；回 claims（sub/email/name/picture…）
        return id_token.verify_oauth2_token(token, _req, settings.google_client_id)
    except Exception:
        return None

async def current_user(authorization: str | None = Header(None)) -> dict | None:
    """有合法 token → 回 claims；否則回 None（匿名，保 Demo / 斷網 / token-free CI）。"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return _verify(authorization[7:])
```

### 4-3. Firestore store
`src/polaris/user_store.py`（新）
```python
from google.cloud import firestore

_db = firestore.Client()  # 用 ADC / runtime SA，免金鑰

def save_session(uid: str, doc: dict) -> str:
    ref = _db.collection("users").document(uid).collection("sessions").document()
    ref.set({**doc, "created_at": firestore.SERVER_TIMESTAMP})
    return ref.id

def list_sessions(uid: str, limit: int = 50) -> list[dict]:
    q = (_db.collection("users").document(uid).collection("sessions")
         .order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit))
    return [{"id": d.id, **d.to_dict()} for d in q.stream()]

def get_session(uid: str, sid: str) -> dict | None:
    d = _db.collection("users").document(uid).collection("sessions").document(sid).get()
    return {"id": d.id, **d.to_dict()} if d.exists else None

def get_subs(uid: str) -> list[str]:
    d = _db.collection("users").document(uid).get()
    return (d.to_dict() or {}).get("tickers", []) if d.exists else []

def set_subs(uid: str, tickers: list[str]) -> None:
    _db.collection("users").document(uid).set({"tickers": tickers}, merge=True)
```

### 4-4. 端點（api.py 加掛；全部 auth 必填，匿名→401）
```python
from fastapi import Depends, HTTPException
from polaris.auth import current_user
from polaris import user_store

def _uid(user: dict | None) -> str:
    if not user:
        raise HTTPException(401, "需要登入")
    return user["sub"]

@app.post("/history")
def post_history(body: HistoryIn, user=Depends(current_user)):
    rid = user_store.save_session(_uid(user), body.model_dump())
    return {"record_id": rid, "status": "ok"}

@app.get("/history")
def get_history(user=Depends(current_user)):
    return user_store.list_sessions(_uid(user))   # 清單（不含大 payload 也可，視需要瘦身）

@app.get("/history/{sid}")
def get_history_one(sid: str, user=Depends(current_user)):
    s = user_store.get_session(_uid(user), sid)
    if not s:
        raise HTTPException(404, "not found")
    return s                                       # 含 result → 前端完整還原

@app.get("/subscriptions")
def get_subscriptions(user=Depends(current_user)):
    return {"tickers": user_store.get_subs(_uid(user))}

@app.post("/subscriptions")
def post_subscriptions(body: SubsIn, user=Depends(current_user)):
    user_store.set_subs(_uid(user), body.tickers)
    return {"status": "ok", "tickers": body.tickers}
```

---

## 5. 端點契約（前後端對齊）

### `POST /history`　（需 Bearer）
**Request**
```json
{ "origin": "research", "query": "台積電 2026Q1 法說重點", "tickers": ["2330"],
  "result": { "final_answer": "...", "evidence": [], "react_steps": [], "citations": [] } }
```
**Response** `{ "record_id": "abc123", "status": "ok" }`

### `GET /history`　（需 Bearer）→ 清單
```json
[ { "id": "abc123", "origin": "research", "query": "...", "tickers": ["2330"],
    "created_at": "2026-06-18T10:30:00Z", "title": "台積電 2026Q1 法說重點" } ]
```

### `GET /history/{id}`　（需 Bearer）→ 完整還原
```json
{ "id": "abc123", "origin": "research", "query": "...", "tickers": ["2330"],
  "created_at": "2026-06-18T10:30:00Z",
  "result": { "final_answer": "...", "evidence": [], "react_steps": [], "citations": [] } }
```

### `GET /subscriptions` → `{ "tickers": ["2330","2454"] }`
### `POST /subscriptions`　body `{ "tickers": [...] }` → `{ "status":"ok", "tickers":[...] }`

> 欄位名鎖定，改契約＝R2/R3/R7 一起改。

---

## 6. Firestore 資料模型

```
users/{uid}                         # uid = Google sub（穩定、唯一）
  ├─ tickers: ["2330", "2454"]      # 訂閱清單（與 history 共用同一 user doc）
  └─ sessions/{sessionId}           # 活動歷史（Claude-Code 側欄）
        origin: "research" | "peer"
        query:  string
        tickers: string[]
        created_at: timestamp
        result: { final_answer, evidence[], react_steps[], citations[] }   # B 級完整還原
```
- **隔離**：一律以 `uid` 為根 → 使用者只看得到自己的。
- **保留期**：B 級存了問答內容（個資），設 TTL / 定期清理（憲法 III + 隱私）。

---

## 7. 上線前檢查（Definition of Done）

- [ ] R2/PM 建好 OAuth Client，redirect = `https://<vercel-domain>/api/auth/callback/google`
- [ ] Cloud Run 設 `POLARIS_CORS_ORIGINS=https://<vercel-domain>`、`GOOGLE_CLIENT_ID`；SA 加 `roles/datastore.user`
- [ ] 前端 NextAuth 跑通，`session.idToken` 拿得到
- [ ] 帶 Bearer 打 `/research` → 後端取得 `sub`
- [ ] `POST /history` 寫進 Firestore（按 uid）；`GET /history` 列出；`GET /history/{id}` 還原整包
- [ ] **匿名路徑驗過**：不帶 token → `/research` 照回、`/history` 回 401、前端 fallback localStorage（斷網備援不破）
- [ ] secret 全在 Vercel env / Secret Manager，未 commit（憲法 III）
- [ ] 設定頁移除 Magic Link UI

---

## 8. 提醒
- **測試 + Demo 都用登入版**：登入流程在測試期就要能實際操作，Demo 當天展示登入 + 個人歷史。
- **後端驗證仍要「可選」**：無 token = 匿名（**僅** token-free CI 與斷網 / Google 不可達時的降級），否則 CI 與備援會掛 —— 但這是 fallback，不是 Demo 主路徑。
- **`sub` 當主鍵，不要用 email**（email 可變）。
- **Firestore ≠ `polaris_core`**：完全獨立的庫，天然避開「app 不寫 core」的約束。
