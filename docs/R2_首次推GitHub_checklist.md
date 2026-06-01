# R2 — 首次推 GitHub Checklist（polaris-desk-starter）

> W1 Day 1 任務。目標：把 starter repo 安全地推上 GitHub，建好分支保護，讓全隊用 PR 協作。
> 🔑 **最高原則：金鑰 / 資料絕不進 git**。本 checklist 已針對本 repo 量身設計。
> 截至 2026-05-31 掃描：repo 內**只有 `.env.example`、無任何金鑰 / `.env` / PDF / data/**（安全）。

---

## 0. 開始前

- [ ] 已裝 `git`；建議裝 GitHub CLI `gh`（`gh auth login` 登入）
- [ ] 在 repo 目錄：`cd .../polaris-desk-starter`
- [ ] 確認你站在 starter 根目錄（看得到 `pyproject.toml`、`src/`、`docs/`、`.specify/`）

## 1. 起 git + 上演前安全檢查（最重要）

```bash
git init -b main
git add -A
git status --short          # 👀 逐行看一次「要被加進去的檔」
```

逐項確認（缺一不可）：
- [ ] **沒有** `.env`（只能有 `.env.example`）
- [ ] **沒有** `*.key`、`*-service-account.json`、`credentials.json`
- [ ] **沒有** `.claude/settings.local.json` 或任何 `*.local.json`
- [ ] **沒有** `*.pdf`、`data/`、`*.parquet`、`__pycache__/`、`.venv/`、`node_modules/`
- [ ] **有** `.env.example`、`.gitignore`、`README.md`、`CLAUDE.md`、`pyproject.toml`、`src/`、`tests/`
- [ ] **有** `docs/spec-kit/`（11 檔規格 + 導讀 HTML）、`.specify/`（含 `memory/constitution.md`）、`.claude/skills/speckit-*`（這些是要共用的 spec-kit 指令）

雙重保險（這兩行輸出都應為「空」）：
```bash
git ls-files | grep -Ei '(^|/)\.env$|\.key$|service-account|credentials|\.local\.json$'   # 應無輸出
git ls-files | grep -Ei '\.pdf$|^data/'                                                    # 應無輸出
```
- [ ] 兩行都沒輸出 ✅（有輸出 → **先別 commit**，回頭修 `.gitignore` 或 `git rm --cached <檔>`）

## 2. 第一個 commit

```bash
git commit -m "chore: bootstrap Polaris Desk starter (skeleton + spec-kit + constitution)"
```
- [ ] commit 成功

## 3. 建 GitHub repo 並推上去

**先私有**（開發期避免誤洩金鑰；Demo 前要對外再轉 public）。

用 `gh`（一步到位）：
```bash
gh repo create polaris-desk --private --source=. --remote=origin --push
```
或手動：在 GitHub 建空 repo `polaris-desk`（**不要**勾 README/.gitignore）→
```bash
git remote add origin git@github.com:<org-or-you>/polaris-desk.git
git push -u origin main
```
- [ ] GitHub 上看得到檔案，且**確認頁面上沒有任何 key**（再掃一次 `.env` 沒上去）

## 4. 分支保護（對齊 Day-0：main 保護、PR 才能合）

GitHub 網頁：**Settings → Branches → Add branch ruleset / rule**，對 `main`：
- [ ] Require a pull request before merging（至少 **1 個 reviewer**）
- [ ] Require status checks to pass（之後 R5 的 CI 上線後勾它）
- [ ] （建議）Require linear history、Block force pushes

或用 `gh`（需要對 repo 有 admin）：
```bash
gh api -X PUT repos/<org-or-you>/polaris-desk/branches/main/protection \
  -f 'required_pull_request_reviews[required_approving_review_count]=1' \
  -F enforce_admins=true -F required_status_checks= -F restrictions=
```
- [ ] main 已受保護（直接 push 會被擋）

## 5. 邀請隊友 + 收尾

**隊友 GitHub 帳號**（2026-06-01 收齊；你＝R2 施惠棋 是 repo owner，不用邀自己）：

| 角色 | 姓名 | GitHub username |
|---|---|---|
| R1 PM | 郝家銘 | `hbb97tw-netizen` |
| R3 Agent | 謝劼恩 | `officehsieh-afk` |
| R4 資料 | 吳瑾瑜 | `holajennytw` |
| R5 Eval | 楊宗勲 | `Arronyang0416` |
| R6 金融品質 | 黃俊維 | `aa851115tw-tech` |
| R7 Demo 前端 | 李靜雲 | `angelali2026888-blip` |

- [ ] Settings → Collaborators 邀上表 6 人（R1、R3、R4、R5、R6、R7）

或用 `gh` 一次邀完（write 權限，之後各自開 PR）：
```bash
REPO=<org-or-you>/polaris-desk
for u in hbb97tw-netizen officehsieh-afk holajennytw Arronyang0416 aa851115tw-tech angelali2026888-blip; do
  gh api -X PUT "repos/$REPO/collaborators/$u" -f permission=push && echo "invited $u"
done
```
- [ ] 6 人都已邀請（GitHub Settings → Collaborators 看得到 6 個 pending/已接受）
- [ ] 把 repo 連結貼進團隊群組（**只貼連結，不貼任何 key**）
- [ ] 在 GitHub 開 `.env.example`，確認上面**沒有**任何真實值（只是範本）
- [ ] 跟全隊講一次：金鑰只放各自本機 `.env`（已 gitignore）/ 雲端用 Secret Manager

## 6. 之後的日常（全員）

- 不直接推 `main`：每個任務開分支 → PR → 1 人 review → 合
  ```bash
  git switch -c r3/retriever-v0
  # ...改動...
  git push -u origin r3/retriever-v0   # 再到 GitHub 開 PR
  ```
- 開工用 spec-kit：在 Claude Code / Cursor 開 repo → `/speckit-specify` 起第一個功能規格（憲法已預載於 `.specify/memory/constitution.md`）。

---

> ⚠️ 萬一不小心把 key 推上去了：**立刻在該服務後台 revoke / 重新產生那把 key**（光從 git 刪掉不夠，歷史還在）。然後再清 git 歷史。
