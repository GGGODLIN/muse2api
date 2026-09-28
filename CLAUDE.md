# muse2api（個人 fork）

Fork 自 [czg86389-hub/muse2api](https://github.com/czg86389-hub/muse2api)，分岔點 upstream `bc06165`。用途：只在本機 127.0.0.1 跑，給本機 LLM 免費池當一條上游；帳號池只放一個用途單一的 Muse 帳號。

## 本 fork 的 patch（合併上游時逐條確認沒被蓋回去）

1. **移除線上升級、版本檢查與 repo push**：刪掉 `app.py` 原本 1794–2106 行整段（`/admin/update/check`、`/admin/repo/status`、`/admin/update/upgrade`、`/admin/repo/pull`、`/admin/repo/push`，以及它們用的 git／GitHub 抓取函式）。原版會 fetch 作者 GitHub main 覆蓋程式後重啟，而帳號 cookie 就存在這台服務上。`/admin/update/check` 原本還沒掛 auth。
2. **admin.html 停用更新 UI**：`loadRepoStatus()` 與 `upgradeNow()` 開頭直接 return，否則前端會改用瀏覽器直接打 `api.github.com` 兜底。
3. **只綁本機**：`config.py` 預設 host 改 `127.0.0.1`；`docker-compose.yml` 只發佈 `127.0.0.1:18610`；`deploy/muse2api.service` 改 `--host 127.0.0.1`；`.env.example` 同步。Dockerfile 容器內維持 `0.0.0.0`（靠 compose 限制對外）。
4. **拿掉範例金鑰**：compose 原本寫死 `m2a_change_me_to_your_secure_key`，照預設部署的人會共用同一把。改成 `${MUSE2API_KEY:-}`，留空時首次啟動自動生成。
5. **縮擴充權限**：`extension/manifest.json` 的 host_permissions 從全站縮到 muse.ai 與 `127.0.0.1`／`localhost`。
6. `.gitignore` 補 `.venv/`。

## 合併上游前的檢查

上游更新大多是在修 muse.ai 網頁改版造成的解析錯誤。合併前先看 diff，至少確認下面兩項沒有新增：

```bash
git fetch upstream
# 只看上游新增的改動；直接 diff HEAD 會把本 fork 刪掉的段落也算成上游新增
BASE=$(git merge-base HEAD upstream/main)
# 1. 新增的寫死外連網址：預期只有 muse.ai、www.muse.ai、127.0.0.1 與文件用的 your-server-ip
git diff $BASE upstream/main -- '*.py' '*.html' '*.js' | command grep -E '^\+' | command grep -oE 'https?://[a-zA-Z0-9._-]+' | sort | uniq -c
# 2. 新的路由與子程序呼叫
git diff $BASE upstream/main -- '*.py' | command grep -E '^\+.*(@app\.(get|post|put|delete)|subprocess|os\.system|eval\(|exec\()'
```

這兩條只抓得到寫死的網址與明顯的呼叫，動態組出的 URL 要讀 diff 本身。合併後重跑下方驗證。

## 驗證（改完或合併後）

```bash
uv venv -q .venv && uv pip install -q --python .venv/bin/python -r requirements.txt
MUSE2API_HOME=/tmp/m2a-test MUSE2API_KEY=m2a_testkey MUSE2API_PORT=18699 \
  .venv/bin/python -c "import uvicorn,app; uvicorn.run(app.app, host=app.CFG.host, port=app.CFG.port)"
```

預期：`lsof -nP -iTCP:18699 -sTCP:LISTEN` 只有 `127.0.0.1`；上面五個已刪端點回 404；`/v1/models` 不帶 key 回 401、帶 key 回 200；用區網 IP 連不上。

## 已知但尚未處理

- GPT-6 Pro 安全審查（2026-09-28，審未修改的 `bc06165`）找到 12 項＋4 則補洞，裁決與修復狀態見 [docs/security-review-rulings.md](/docs/security-review-rulings.md)。**接進 free 池前必修第 1、2、3、7 條**（參考圖讀本機檔、`--no-sandbox`、跨請求共用對話、串流取消卡死）。修掉一條就把它搬進上面的 patch 清單，並在裁決表標「已修」。
- 帳號風險不因 fork 改變：這是規避 Meta 地區限制並自動操作網頁，帳號可能被封。
