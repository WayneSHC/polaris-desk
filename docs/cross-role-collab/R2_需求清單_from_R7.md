# R2 需求清單（R7 前端提出）

> 整理日期：2026-06-17｜撰寫：R7
> 本文件列出前端需要 R2 決策或協作的事項，含現況說明與前端所需規格。

> ## ✅ R2 決議（2026-06-18）
> 兩項都已拍板，**完整串接做法見 [`Auth-Firestore_串接指南_R2決議.md`](./Auth-Firestore_串接指南_R2決議.md)**。
>
> | # | 項目 | 決議 |
> |---|---|---|
> | 1 | Auth 框架 | **NextAuth.js + Google OAuth**；後端 app 層驗 Google id_token（`aud`=client_id），`sub` 當使用者主鍵 |
> | 1 | **Magic Link** | ❌ **砍**（只 Google OAuth；省寄信服務一個坑）→ R7 移除設定頁 Magic Link UI |
> | 2 | 紀錄 / 訂閱儲存 | **Firestore**（GCP 原生、同專案、per-user 文件型；**不寫 `polaris_core`**）；history + subscriptions 共用 |
> | 2 | 紀錄深度 | **B 級完整還原**：每筆 session 存整包 `result`，點開直接還原當時答案 |
> | — | 時程 | **測試期就接、Demo 用登入版**；無 token 匿名僅作 CI / 斷網降級（非預設） |
> | — | 金鑰 | client secret / NextAuth secret → Secret Manager；後端只吃 `GOOGLE_CLIENT_ID` |

---

## 1. 使用者認證（Auth）— Google OAuth ~~+ Magic Link~~（Magic Link 已砍）

### 現況

設定頁（`/settings`）已有兩個登入 UI：
1. **Google OAuth 按鈕**：點擊無反應，純 UI
2. **工作郵箱 Magic Link 表單**：送出後只在前端 mock `setSent(true)`，未真正寄信

兩個登入方式都需要 R2 先決策架構，R7 再接前端部分。

### 待確認事項

| 決策項目 | 選項建議 | 說明 |
|----------|----------|------|
| **Auth 框架** | NextAuth.js（推薦）/ 自建 JWT | NextAuth.js 原生支援 Next.js，Provider 設定簡單，session 管理完整 |
| **Session 儲存** | JWT（stateless）/ 資料庫 session | MVP 用 JWT 即可，不需新增 BQ 表 |
| **Google OAuth 憑證** | Google Cloud Console 建立 OAuth App | 需設定 Callback URL：`https://<domain>/api/auth/callback/google` |
| **Magic Link 寄信服務** | Resend / SendGrid / Gmail SMTP | 需要寄件 API key，存入 Secret Manager |

### 前端串接所需資訊（確認後提供）

```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
NEXTAUTH_SECRET=...           # 隨機字串，用於 JWT 簽名
NEXTAUTH_URL=https://...      # 部署後的前端網址

# Magic Link（選填，若要實作）
EMAIL_SERVER_HOST=...
EMAIL_SERVER_PORT=...
EMAIL_FROM=noreply@polaris.dev
```

以上填入 `.env`，R7 接到這些 key 後即可完成前端串接。

### 前端接線計畫（確認架構後實作）

- `src/app/api/auth/[...nextauth]/route.ts`：NextAuth API route（R2 確認架構後 R7 建立）
- 設定頁 Google 按鈕：`signIn("google")` 呼叫
- 設定頁登出按鈕：`signOut()` 呼叫
- `AppShell` 顯示真實登入用戶名稱與頭像（目前是 hardcoded "Jing Chen"）
- Magic Link 表單：呼叫 `POST /auth/email` 或 NextAuth Email Provider

### 若不用 NextAuth，前端需要的端點

若選擇自建 auth（不用 NextAuth.js），前端需要以下端點：

| 方法 | 路徑 | 說明 |
|------|------|------|
| `POST` | `/auth/google` | 接收前端的 Google ID token，驗證後回傳 session token |
| `POST` | `/auth/email` | 接收 email，寄送 Magic Link |
| `GET`  | `/auth/me` | 回傳當前登入用戶資訊（name、email、avatar） |
| `POST` | `/auth/logout` | 清除 session |

---

## 2. 對話紀錄永久儲存（POST /history）

> ✅ **R2 決議**：儲存後端＝**Firestore**（B 級完整還原，存整包 `result`）；與訂閱清單共用。
> 不寫 `polaris_core`。端點規格與資料模型見 [`Auth-Firestore_串接指南_R2決議.md`](./Auth-Firestore_串接指南_R2決議.md) §5/§6。

### 現況

對話紀錄目前使用 `localStorage` 暫存（R7 自行實作的 MVP），使用者換瀏覽器或清快取後紀錄消失。

### 問題

永久儲存需要後端資料庫，但 `polaris_core` 是唯讀共用庫，不適合存使用者個人資料。需要 R2 決定：

| 選項 | 說明 | 適合情境 |
|------|------|----------|
| **A. BQ 新 dataset** | 建 `polaris_users` dataset，存 history、subscriptions | 已有 BQ 基礎設施，成本低 |
| **B. Firestore** | NoSQL，讀寫簡單，即時同步 | 需要多裝置同步、即時更新 |
| **C. 維持 localStorage** | 不需後端，但無法跨裝置 | MVP 可接受，短期內夠用 |

### R7 目前的 localStorage 實作

```
src/lib/historyStore.ts   ← 讀寫 localStorage
src/lib/api.ts            ← api.history() 改讀 localStorage
```

研究助理頁與同業比較頁查詢完成後自動寫入，對話紀錄頁點擊跳轉已完成。

### 確認架構後，前端需要的端點

```
POST /history   { origin, query, tickers, timestamp } → { record_id, status }
GET  /history   → [{ id, query, page, time, tags }]
```

詳細規格見 `docs/cross-role-collab/R3_需求清單_from_R7.md` §7。

---

## 優先級

| # | 項目 | 優先 | 狀態 |
|---|------|------|------|
| 1 | Auth 架構決策（Google OAuth；Magic Link 砍） | 🔴 高 | ✅ 已決議（NextAuth + Google OAuth）→ R7 接線 |
| 2 | 對話紀錄永久儲存方案 | 🟡 中 | ✅ 已決議（Firestore, B 級）→ R3 接端點 + R7 切換 |
