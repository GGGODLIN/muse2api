# GPT-6 Pro 安全審查：逐條裁決（2026-09-28）

原文見 [security-review-2026-09-28.md](/docs/security-review-2026-09-28.md)。行號以 upstream `bc06165` 為準；「已核對」表示本 fork 已用 grep 確認該行內容與審查描述一致。狀態欄記錄是否已在 fork 修掉。

| # | 顧問意見 | 嚴重度 | 裁決 | 依據／要做的事 | 狀態 |
|---|---|---|---|---|---|
| 1 | 參考圖欄位會讀本機檔案（`os.path.isfile` → `open`），HTTP 分支可 SSRF | 高 | 接受 | 已核對 `engine.py:961–963`。本 fork 用途是文字上游：停用 images／videos 路由；保留時刪本機路徑分支並限制下載目的地 | 已修；tests/verify_fork.py T6＋媒體路由實測 404 |
| 2 | 主引擎 Chromium 帶 `--no-sandbox` | 高 | 接受 | 已核對 `engine.py:65`。移除該旗標；實作時要實測 macOS headless 不帶它能否啟動 | 已修；T5 實際啟動 Chrome 154 |
| 3 | 不同 API 請求共用同一條 Muse 對話，重設失敗被吞 | 中 | 待驗證 | 接進 free 池後跨任務資料會互相看到。每個請求開新對話，重設失敗就回錯。2026-09-28 使用者決定先實測：同一段多輪對話分別跑「重用」與「開新」，比首字延遲與設定頁用量百分比，再決定改不改 | 未修 |
| 4 | CDP 發現埠上已有瀏覽器就直接接管；`--remote-allow-origins=*` | 中 | 接受 | 已核對 `engine.py:70–71`。埠被未知程序占用就停止；移除 Origin 萬用字元 | 已修；T4、T5、T7 |
| 5 | 帳號標籤放進 inline `onclick` 字串，HTML 編碼擋不住 JS 語境 | 中 | 接受 | 已核對 `admin.html:1061`。改用 `addEventListener` 傳資料 | 已修；僅 grep 確認沒有 label 進 JS 字串，未在瀏覽器實測 |
| 6 | 媒體下載兜底不驗檔案類型，與管理面板同源提供 | 中 | 接受 | 若照第 1 條停用媒體路由即一併消除；保留媒體時才需另修 | 已修（隨第 1 條停用媒體路由，實測 404） |
| 7 | 串流 worker 持鎖時呼叫無 timeout 的 `q.put()`，下游斷線可永久卡死 | 中 | 接受 | 已核對 `app.py:219、255、277、279`。relay 逾時或取消是常態，接 free 池前必修：put 加短 timeout 並檢查取消 | 已修；T3（原版同測試 FAIL） |
| 8 | 重新注入 cookie 時沒保留 HttpOnly／SameSite，domain 被擴大 | 中 | 接受 | 核心登入 cookie 明確設 `httpOnly=True`，保留原 domain 範圍 | 已修；未實測（要真帳號注入後讀回 cookie 屬性） |
| 9 | 介面旋轉 Key 後，環境變數優先於 `.env`，重啟可能讓舊 Key 復活 | 中 | 接受（最小做法） | 本 fork 的 Key 由啟動環境提供；停用介面旋轉，或旋轉時提示要改啟動設定 | 已修；HTTP 實測 rotate 回 409 |
| 10 | `_persist_env` 會把 `.env` 權限變成 0644；Key 與 cookie 會印進日誌／終端 | 低 | 接受 | `.env` 改用安全暫存檔寫入；不印完整 Key／cookie；資料目錄 0700 | 已修；T2（原版同測試 0644）；資料目錄實測 0700 |
| 11 | CORS 解析了設定卻固定 `allow_origins=["*"]` | 低 | 接受 | 已核對 `app.py:67、71`。本機 relay 不需要跨站，直接移除 CORS 開放 | 已修；HTTP 實測 evil.com 無 ACAO、muse.ai 放行 |
| 12 | 依賴只有 `>=` 下限，Docker 用可變 tag | 低 | 接受 | 首次接進日常路徑前產生 lockfile，記錄 Chromium 版本 | 已修；requirements.lock（含 hash）；Dockerfile 仍用 requirements.txt、Chromium 版本未記錄 |
| 補 1 | 前端也有直連 GitHub 的備援檢查與定時呼叫 | — | 已處理 | `loadRepoStatus()` 開頭已直接 return，所有呼叫點（含定時）都變成空操作 | 已修（`0e1cc9e`） |
| 補 2 | 改 `config.py` 不會覆蓋 Dockerfile 寫死的 `--host 0.0.0.0` | — | 拒絕修改 Dockerfile | 刻意保留：容器內必須 0.0.0.0，對外由 compose 的 `127.0.0.1:18610` 限制（見 CLAUDE.md patch 3）；顧問同段也建議這樣做 | 不改 |
| 補 3 | `auth()` 在 Key 為空時直接放行 | — | 接受 | 已核對 `app.py:168–169`。改成空 Key 一律拒絕 | 已修；T1（原版同測試放行） |
| 補 4 | cookie 助手也信任指定埠的 CDP，失敗時印出 cookie；擴充會從任意 `/admin` 頁猜上傳目的地 | — | 接受 | 優先用 `tools/get_muse_cookie.py` 並修掉列印；擴充固定只上傳到 127.0.0.1 | 已修；未實測（cookie 助手與擴充都要真登入流程） |

顧問的整體建議是先做「文字專用、每請求獨立對話、受限 CDP、可靠取消」的最小版本，再考慮接 free 池。與本 fork 原本的判斷一致，差別在：原本只處理了供應鏈與網路暴露三項，沒有涵蓋第 1、2、3、7 條。
