"""fork 安全修補的回歸驗證；合併上游後跑：.venv/bin/python tests/verify_fork.py

T5 會用本機 Google Chrome 開一個獨立暫存 profile 的 headless 視窗。
"""
import http.server
import json
import os
import stat
import sys
import tempfile
import threading
import time

HOME = tempfile.mkdtemp(prefix="m2a-verify-")
os.environ["MUSE2API_HOME"] = HOME
os.environ["MUSE2API_PROFILE_ROOT"] = os.path.join(HOME, "profiles")
os.environ["MUSE2API_KEY"] = "m2a_testkey"
os.environ["MUSE2API_CHROMIUM"] = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)

import app  # noqa: E402
import engine as engmod  # noqa: E402
from cdp import CDP, CDPError  # noqa: E402
from fastapi import HTTPException  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


# T1 empty key must be rejected
saved = app.CFG.api_key
app.CFG.api_key = ""
try:
    app.auth(None)
    check("auth 空 key 拒絕", False, "returned")
except HTTPException as e:
    check("auth 空 key 拒絕", e.status_code == 503, f"status={e.status_code}")
app.CFG.api_key = saved

# T2 .env stays 0600 under umask 022
os.umask(0o022)
envp = os.path.join(app.CFG.base_dir, ".env")
open(envp, "w").close()
os.chmod(envp, 0o600)
app._persist_env("FOO", "bar")
mode = stat.S_IMODE(os.stat(envp).st_mode)
check(".env 寫回後仍 0600", mode == 0o600, oct(mode))

# T3 cancelled stream must release GEN_LOCK
app.engine.start = lambda: None
app._renew_and_persist = lambda *a, **k: None
app.store.mark = lambda *a, **k: None
app._sync_cookies = lambda *a, **k: None


def fake_stream(*a, **k):
    for i in range(1000):
        yield f"chunk{i}"


app.engine.chat_stream = fake_stream
gen = app.safe_chat_stream({}, "hi", None, 30, "acc1")
first = next(gen)
time.sleep(1.0)  # 讓 worker 先把 maxsize=100 的佇列塞滿，才是會卡死的情境
gen.close()
released = False
for _ in range(50):
    if app.GEN_LOCK.acquire(blocking=False):
        app.GEN_LOCK.release()
        released = True
        break
    time.sleep(0.1)
check("串流取消後 5 秒內釋放 GEN_LOCK", released and first == "chunk0", f"first={first}")

# T4 refuse to attach to a CDP port we did not launch
class Fake(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"webSocketDebuggerUrl": "ws://127.0.0.1:1/devtools/browser/x"}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 19298), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
cfg = app.CFG
cfg.cdp_port = 19298
eng = engmod.MuseEngine(cfg)
try:
    eng.start()
    check("CDP 埠被占用時拒絕接管", False, "attached")
except engmod.MuseGenerationError as e:
    check("CDP 埠被占用時拒絕接管", "拒絕接管" in str(e), str(e)[:60])
srv.shutdown()

# T5 real Chrome launch without --no-sandbox / --remote-allow-origins, CDP connect w/o Origin
cfg.cdp_port = 19297
eng = engmod.MuseEngine(cfg)
try:
    eng.start()
    ver = eng.browser.send("Browser.getVersion")["result"]["product"]
    check("Chrome 無 --no-sandbox 啟動並經 CDP 連線", True, ver)
except Exception as e:  # noqa: BLE001
    check("Chrome 無 --no-sandbox 啟動並經 CDP 連線", False, repr(e)[:120])
finally:
    eng.stop()

# T6 reference image normalizer
n = engmod.MuseEngine._normalize_image
check("參考圖拒絕 URL", n("http://169.254.169.254/latest") == ("", "image/png"))
check("參考圖拒絕本機路徑", n(envp) == ("", "image/png"))
check("參考圖接受 data URI", n("data:image/png;base64,QUJD") == ("QUJD", "image/png"))

# T7 CDP client refuses non-loopback websocket
try:
    CDP("ws://example.com:9222/devtools/browser/x", timeout=2)
    check("CDP 拒絕非本機 WebSocket", False, "connected")
except CDPError:
    check("CDP 拒絕非本機 WebSocket", True)
except Exception as e:  # noqa: BLE001
    check("CDP 拒絕非本機 WebSocket", False, repr(e)[:80])

for name, ok, detail in results:
    print(("PASS" if ok else "FAIL"), name, detail)
print("SUMMARY", sum(ok for _, ok, _ in results), "/", len(results))
