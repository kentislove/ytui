"""v3.0 整合測試：真的啟動後端（暫存資料庫、測試連接埠），用 HTTP 測登入保護、提問、額度、紀錄、管理頁。
會真的呼叫 AI 1 次。用法：.venv\\Scripts\\python.exe test_api.py
（跳過 Google：直接在暫存資料庫建立一個登入憑證，模擬「已經用 Google 登入」）
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
PORT = 5199
BASE = f"http://127.0.0.1:{PORT}"
FRAMES = HERE.parents[1] / "phase0_實測" / "v8_新影片驗證" / "frames" / "E_平結教學_60s"

data_dir = tempfile.mkdtemp()
env = {**os.environ, "DATA_DIR": data_dir, "DAILY_LIMIT": "1", "FREE_USERS_LIMIT": "50",
       "ADMIN_EMAILS": "boss@test.local", "GOOGLE_CLIENT_ID": "test-client"}
os.environ.update(env)
import accounts as A   # noqa: E402  先設好環境變數再載入，才會用暫存資料庫

acc = A.Accounts(A.load_settings())
acc.add_invite("friend@test.local", "測試", "test")   # v3.3：要先在邀請名單上才能登入
friend_token, _ = acc.login({"sub": "f1", "email": "friend@test.local", "name": "朋友"})
boss_token, _ = acc.login({"sub": "b1", "email": "boss@test.local", "name": "管理者"})
acc.db.close()


def call(path, body=None, token=None, method=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers, method=method or ("POST" if body is not None else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.startswith(("{", "[")) else raw)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


ok = True
def check(cond, msg):
    global ok
    print(("  ✅ " if cond else "  ❌ ") + msg)
    ok &= bool(cond)


server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(PORT)],
                          cwd=HERE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/api/config", timeout=2)
            break
        except Exception:
            time.sleep(0.5)

    print("1. 不用登入的")
    s, d = call("/api/config")
    check(s == 200 and d["google_client_id"] == "test-client", "設定：回傳用戶端 ID")
    s, d = call("/")
    check(s == 200 and "YouTube AI" in d, "網頁首頁可以打開")
    s, d = call("/docs")
    check(s == 404, "自動 API 文件頁已關閉（不對外公開介面細節）")

    print("2. 沒登入一律擋下")
    for path, body in [("/api/me", None), ("/api/history", None), ("/api/ask", {"video_id": "x", "pause": 0, "question": "q"})]:
        s, d = call(path, body)
        check(s == 401 and d["error"] == "login_required", f"{path} → 401 請先登入")
    s, d = call("/api/me", token="random-guess-token-123")
    check(s == 401, "亂猜的憑證 → 401")

    print("3. 朋友登入後提問（真的呼叫 AI）")
    s, d = call("/api/me", token=friend_token)
    check(s == 200 and d["user"]["quota"]["remaining"] == 1, "今天剩 1 題（測試設每天 1 題）")
    frames = [{"t": int(f.stem.split("_")[1].rstrip("s")),
               "data_url": "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()}
              for f in sorted(FRAMES.glob("*.jpg"))]
    body = {"video_id": "3Z9BBSL-iSU", "title": "【gusta編織學堂】傘繩平結編織教學", "pause": 60,
            "question": "這裡繩子要從上面還是下面穿？", "frames": frames,
            "subtitles": [{"start": 56, "end": 59, "text": "在將右線段穿過主線的最下面後"},
                          {"start": 59, "end": 61, "text": "從左邊的洞裡穿出"}], "lang": "zh-TW"}
    s, d = call("/api/ask", body, token=friend_token)
    check(s == 200 and d.get("answer"), f"回答成功（{d.get('model')}，{d.get('secs')} 秒）")
    print("     ", (d.get("answer") or str(d))[:120].replace("\n", " "))
    check(d.get("quota", {}).get("remaining") == 0, "回答後額度剩 0")
    s, d = call("/api/ask", body, token=friend_token)
    check(s == 429 and d["error"] == "quota", f"第 2 題被擋：{d.get('message')}")

    print("4. 紀錄存在伺服器")
    s, d = call("/api/history", token=friend_token)
    check(s == 200 and len(d["items"]) == 1 and d["items"][0]["question"].startswith("這裡繩子"), "朋友有 1 筆紀錄")
    s, d = call("/api/history", token=boss_token)
    check(s == 200 and d["items"] == [], "管理者看不到朋友的紀錄")

    print("5. 管理頁")
    s, d = call("/api/admin/users", token=friend_token)
    check(s == 403, "朋友打不開管理頁")
    s, d = call("/api/admin/users", token=boss_token)
    check(s == 200 and [u["email"] for u in d["users"]] == ["friend@test.local", "boss@test.local"], "管理者看到 2 位使用者")
    friend_id = d["users"][0]["id"]
    s, _ = call(f"/api/admin/users/{friend_id}/status", {"status": "disabled"}, token=boss_token)
    s2, _ = call("/api/me", token=friend_token)
    check(s == 200 and s2 == 401, "管理者停用朋友後，朋友立刻被登出")

    print("5b. v3.3 邀請名單 API")
    s, d = call("/api/admin/invites", token=friend_token)
    check(s == 401 or s == 403, "朋友（已被停用）打不開邀請名單")
    s, d = call("/api/admin/invites", {"email": "new@test.local", "note": "新朋友"}, token=boss_token)
    check(s == 200 and d["added"] is True, "管理者加入 new@test.local")
    s, d = call("/api/admin/invites", {"email": "NEW@test.local"}, token=boss_token)
    check(s == 200 and d["added"] is False, "大寫重複加入 → 不會重複")
    s, d = call("/api/admin/invites", {"email": "不是email"}, token=boss_token)
    check(s == 422, "格式不對的 Email → 拒絕")
    s, d = call("/api/admin/invites", token=boss_token)
    check(s == 200 and "new@test.local" in [i["email"] for i in d["invites"]], "名單裡看得到 new@test.local")
    s, d = call("/api/admin/invites/boss%40test.local", token=boss_token, method="DELETE")
    check(s == 400, "管理者自己不能被移除")
    s, d = call("/api/admin/invites/new%40test.local", token=boss_token, method="DELETE")
    check(s == 200 and d["removed"] is True, "移除 new@test.local")

    print("6. 登出")
    call("/api/auth/logout", {}, token=boss_token)
    s, _ = call("/api/me", token=boss_token)
    check(s == 401, "登出後憑證失效")
finally:
    server.terminate()
    server.wait(timeout=10)
    print("（測試用後端已關閉）")

print("\n全部通過 ✅" if ok else "\n有測試失敗 ❌")
