# muse2api（個人 fork）

Fork 自 [czg86389-hub/muse2api](https://github.com/czg86389-hub/muse2api)，分岔點 upstream `bc06165`。用途：只在本機 127.0.0.1 跑，給本機 LLM 免費池當一條上游；帳號池只放一個用途單一的 Muse 帳號。

## 本 fork 的 patch（合併上游時逐條確認沒被蓋回去）

1. **移除線上升級、版本檢查與 repo push**：刪掉 `app.py` 原本 1794–2106 行整段（`/admin/update/check`、`/admin/repo/status`、`/admin/update/upgrade`、`/admin/repo/pull`、`/admin/repo/push`，以及它們用的 git／GitHub 抓取函式）。原版會 fetch 作者 GitHub main 覆蓋程式後重啟，而帳號 cookie 就存在這台服務上。`/admin/update/check` 原本還沒掛 auth。
2. **admin.html 停用更新 UI**：`loadRepoStatus()` 與 `upgradeNow()` 開頭直接 return，否則前端會改用瀏覽器直接打 `api.github.com` 兜底。
3. **只綁本機**：`config.py` 預設 host 改 `127.0.0.1`；`docker-compose.yml` 只發佈 `127.0.0.1:18610`；`deploy/muse2api.service` 改 `--host 127.0.0.1`；`.env.example` 同步。Dockerfile 容器內維持 `0.0.0.0`（靠 compose 限制對外）。
4. **拿掉範例金鑰**：compose 原本寫死 `m2a_change_me_to_your_secure_key`，照預設部署的人會共用同一把。改成 `${MUSE2API_KEY:-}`，留空時首次啟動自動生成。
5. **縮擴充權限**：`extension/manifest.json` 的 host_permissions 從全站縮到 muse.ai 與 `127.0.0.1`／`localhost`。
6. `.gitignore` 補 `.venv/`。
7. **只當文字上游**：`/v1/images/*`、`/v1/videos` 掛 `media_disabled` 回 404；`engine._normalize_image` 只收內嵌 data，拒絕 URL 與本機路徑（原版會下載任意 URL、讀任意檔送進 Muse）。
8. **Chromium 不關沙盒、不接管別人的瀏覽器**：拿掉 `--no-sandbox` 與 `--remote-allow-origins=*`；CDP 埠已有瀏覽器就報錯；`cdp.py` 只連本機 WebSocket 並用 `suppress_origin=True`（不帶 Origin，Chrome 才肯在沒有萬用 Origin 時接受）。
9. **串流取消不卡死**：`safe_chat_stream` 的佇列寫入改成帶 timeout 並檢查 `stop_event`；原版下游斷線且佇列滿時會永遠持有 `GEN_LOCK`。
10. **登入 cookie 保持 HttpOnly**：`_apply_cookies` 對 `HTTPONLY_COOKIES` 設 `httpOnly`。
11. **授權與設定**：空 Key 時 `auth()` 回 503 而非放行；停用介面旋轉 Key（回 409，環境變數優先於 `.env`，旋轉撐不過重啟）；CORS 套用 `MUSE2API_CORS_ORIGINS`，未設時只放行 `https://muse.ai`。
12. **秘密檔案**：`.env` 用 `mkstemp` 寫回保持 0600；資料、媒體、profile 目錄 0700；啟動日誌不印完整 Key。
13. **Cookie 助手與擴充**：`tools/get_muse_cookie.py` 調試埠已被占用就退出、profile 用 `mkdtemp`、上傳失敗不印 cookie；擴充不再從分頁猜上傳目的地，只准上傳到 127.0.0.1／localhost，訊息改用 textContent。
14. **管理面板 XSS**：改名、刪除按鈕的帳號標籤改放 `data-label`，不再拼進 inline `onclick` 的 JS 字串。
15. `requirements.lock`：`uv pip compile --generate-hashes` 產生的鎖檔（Dockerfile 尚未改用）。

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

預期：`lsof -nP -iTCP:18699 -sTCP:LISTEN` 只有 `127.0.0.1`；上面五個已刪端點回 404；`/v1/models` 不帶 key 回 401、帶 key 回 200；用區網 IP 連不上；媒體路由回 404；`/admin/apikey/rotate` 回 409。

單元層的回歸跑 `.venv/bin/python tests/verify_fork.py`，預期 `SUMMARY 9 / 9`。它會用本機 Google Chrome 開一個暫存 profile 的 headless 視窗驗 patch 8。T3（串流取消）要先讓佇列塞滿再斷線才重現得出原版的卡死，改測試時別拿掉那個 `sleep`。

## 已知但尚未處理

- GPT-6 Pro 安全審查（2026-09-28，審未修改的 `bc06165`）找到 12 項＋4 則補洞，裁決與修復狀態見 [docs/security-review-rulings.md](/docs/security-review-rulings.md)。除第 3 條外都已修（上面 patch 7–15）。
- **第 3 條未修：每個請求仍可能沿用同一條 Muse 對話**（`engine.reset_thread(for_chat=True)` 在氣泡數 < 16 時重用）。`build_chat_prompt` 每次都送完整歷史，所以重用會讓歷史在 Muse 端重複堆疊，也會讓不同 agent 的任務互相看得到。使用者 2026-09-28 決定先用真帳號實測「重用 vs 開新」的首字延遲與用量百分比再決定。接進 free 池前要先有結論。
- 未用真帳號跑過任何端到端流程：cookie 注入後的 HttpOnly、cookie 助手、擴充都只做了靜態檢查。
- 帳號風險不因 fork 改變：這是規避 Meta 地區限制並自動操作網頁，帳號可能被封。
