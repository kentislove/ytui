"""v3.1 網頁版提問 /api/ask_video 整合測試（真的呼叫 Gemini 約 3–4 次）。
用法：.venv\\Scripts\\python.exe test_api_video.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
PORT = 5198
BASE = f"http://127.0.0.1:{PORT}"
env = {**os.environ, "DATA_DIR": tempfile.mkdtemp(), "DAILY_LIMIT": "5", "ADMIN_EMAILS": "", "GOOGLE_CLIENT_ID": "test"}
os.environ.update(env)
import accounts as A   # noqa: E402

acc = A.Accounts(A.load_settings())
acc.add_invite("friend@test.local", "測試", "test")   # v3.3：要先在邀請名單上才能登入
token, _ = acc.login({"sub": "f1", "email": "friend@test.local", "name": "朋友"})
acc.db.close()


def call(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=330) as r:
            return r.status, json.loads(r.read().decode()), round(time.time() - t, 1)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode()), round(time.time() - t, 1)


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

    print("1. 公開影片：Gemini 直接看片段（咖哩塊 4:42，倒進容器定型）")
    s, d, secs = call("/api/ask_video", {"video_id": "YDaqymcDRLw", "pause": 282, "question": "現在把咖哩倒進什麼容器？",
                                        "can_share": True})
    check(s == 200 and d.get("video_used"), f"HTTP {s}，看了影片={d.get('video_used')}，{d.get('model')}，{secs} 秒")
    check(bool(d.get("title")), f"後端自己讀到影片標題：{d.get('title', '')[:30]}")
    times = re.findall(r"(\d{1,2}):([0-5]\d)", d.get("answer", ""))
    abs_ok = all(258 <= int(m) * 60 + int(s_) <= 300 for m, s_ in times) if times else True
    check(abs_ok, f"回答裡的時間都在影片原本的時間軸附近（{['%s:%s' % t for t in times]}）")
    print("     ", d.get("answer", str(d))[:200].replace("\n", " "))
    check(d.get("quota", {}).get("remaining") == 4, "扣 1 題，剩 4 題")

    print("2. 看不了的影片＋電腦（能分享畫面）→ 409 請網頁截圖，不扣額度")
    s, d, secs = call("/api/ask_video", {"video_id": "aaaaaaaaaaa", "pause": 30, "question": "這在做什麼？", "can_share": True})
    check(s == 409 and d.get("error") == "need_frames", f"HTTP {s}：{d.get('message')}（原因 {d.get('reason')}，{secs} 秒）")
    check(d.get("quota", {}).get("remaining") == 4, "沒有扣額度")

    print("3. 看不了的影片＋手機（不能分享畫面）→ 改用文字回答並註明")
    s, d, secs = call("/api/ask_video", {"video_id": "aaaaaaaaaaa", "pause": 30, "question": "這在做什麼？",
                                        "title": "測試影片", "can_share": False})
    check(s == 200 and not d.get("vision_used"), f"HTTP {s}，{d.get('model')}，{secs} 秒")
    check("沒有看到畫面" in d.get("answer", ""), "回答開頭註明沒看到畫面")
    print("     ", d.get("answer", str(d))[:160].replace("\n", " "))

    print("4. 網址格式不對 → 400")
    s, d, _ = call("/api/ask_video", {"video_id": "../../etc", "pause": 1, "question": "q"})
    check(s == 400, f"HTTP {s}：{d.get('message')}")
finally:
    server.terminate()
    server.wait(timeout=10)
    print("（測試用後端已關閉）")

print("\n全部通過 ✅" if ok else "\n有測試失敗 ❌")
