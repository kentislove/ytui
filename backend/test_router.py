"""自動切換規則的離線測試（不連網、不用金鑰）。用法：.venv\\Scripts\\python.exe test_router.py"""
import tempfile
from pathlib import Path

import ai_router as R

CANDS = [R.Candidate("gemini", "flash-lite", True, search=True), R.Candidate("gemini", "flash", True),
         R.Candidate("groq", "llama-4-scout", True), R.Candidate("openrouter", "gemma-4-31b:free", True),
         R.Candidate("groq", "llama-3.3-70b", False), R.Candidate("openrouter", "nemotron:free", False)]


def make_router():
    r = R.Router.__new__(R.Router)
    r.keys = {"GEMINI_API_KEY": "x", "GROQ_API_KEY": "x", "OPENROUTER_API_KEY": "x"}
    r.state = R.State(Path(tempfile.mkdtemp()) / "state.json")
    r.cands, r.discovered_at = list(CANDS), 9e18
    return r


def fake(behaviour: dict):
    """behaviour：模型名稱 → 'ok' 或錯誤（例如 '429-daily'）。沒列到的一律 ok。"""
    calls = []

    def call_fn(c, keys, system, text, images, search, timeout):
        calls.append((c.model, bool(images), search))
        b = behaviour.get(c.model, "ok")
        if b == "ok":
            return f"答案來自 {c.model}", 100, 50
        code, _, kind = b.partition("-")
        detail = {"daily": "Quota exceeded: requests per day", "img": "model does not support image input"}.get(kind, "")
        raise R.CallError(code, detail)
    return call_fn, calls


def run(name, router, behaviour, web=False):
    fn, calls = fake(behaviour)
    res = router.ask("sys", "有畫面", "沒畫面", ["IMG"], web_search=web, call_fn=fn)
    return res, calls


ok = True
def check(cond, msg):
    global ok
    print(("  ✅ " if cond else "  ❌ ") + msg)
    ok &= cond


print("1. 前兩個失敗（每日額度、503），第三個成功")
r = make_router()
res, calls = run("1", r, {"flash-lite": "429-daily", "flash": "503"})
check(res.model == "groq:llama-4-scout", f"由 {res.model} 回答")
check([a.status for a in res.attempts] == ["429", "503", "ok"], f"嘗試紀錄 {[a.status for a in res.attempts]}")
check(r.state.cool["gemini:flash-lite"] > R.time.time() + 3600, "每日額度用完的模型冷卻到隔天")

print("2. 所有看圖模型都 429 → 改用文字模型，並註明沒看畫面")
r = make_router()
res, calls = run("2", r, {"flash-lite": "429", "flash": "429", "llama-4-scout": "429", "gemma-4-31b:free": "429"})
check(res.model == "groq:llama-3.3-70b" and res.vision_used is False, f"由 {res.model} 回答，看畫面={res.vision_used}")
check(calls[-1][1] is False, "文字模型沒有收到圖片")

print("3. 全部失敗 → 沒有答案，而且每個模型都試過")
r = make_router()
allfail = {c.model: "503" for c in CANDS}
res, calls = run("3", r, allfail)
check(res.answer == "", "沒有答案")
check({m for m, _, _ in calls} == {c.model for c in CANDS}, f"6 個模型全部試過（實際 {len(set(m for m, _, _ in calls))} 個）")

print("4. 上一題全部失敗、模型都在冷卻 → 下一題仍會把冷卻中的全部再試（第 2 輪）")
res, calls = run("4", r, {"flash": "ok", **{k: v for k, v in allfail.items() if k != "flash"}})
check(res.model == "gemini:flash", f"冷卻中的模型也被重試，由 {res.model} 回答")

print("5. 模型不支援圖片 → 記下來，之後改當文字模型用")
r = make_router()
res, calls = run("5", r, {"flash-lite": "400-img"})
check("gemini:flash-lite" in r.state.no_vision, "已標記為不支援圖片")
check(res.model == "gemini:flash", f"由 {res.model} 回答")

print("6. 金鑰無效（401）→ 整家跳過，紀錄中註明")
r = make_router()
res, calls = run("6", r, {"flash-lite": "401", "llama-4-scout": "503"})
check([a.status for a in res.attempts][:3] == ["401", "key_invalid", "503"], f"嘗試紀錄 {[a.status for a in res.attempts][:4]}")
check(res.model == "openrouter:gemma-4-31b:free", f"由 {res.model} 回答")

print("7. 勾選查網路 → 能搜尋的模型優先，且有開搜尋")
r = make_router()
r.cands = [R.Candidate("groq", "llama-4-scout", True), R.Candidate("gemini", "flash-lite", True, search=True)]
res, calls = run("7", r, {}, web=True)
check(calls[0] == ("flash-lite", True, True) and res.searched, f"第一個呼叫 {calls[0]}，有查網路={res.searched}")

print("7b. v2.1：模型沒真的搜尋 → 不標示有查網路；有搜尋 → 帶回參考網站")
r = make_router()
r.cands = [R.Candidate("gemini", "flash-lite", True, search=True)]
res, _ = run("7b", r, {}, web=True)   # fake 回 3 個值＝舊格式，視為有搜尋
r2 = make_router()
r2.cands = [R.Candidate("gemini", "flash-lite", True, search=True)]
res2 = r2.ask("sys", "a", "b", ["IMG"], web_search=True, call_fn=lambda *a: ("答", 1, 1, None))
res3 = r2.ask("sys", "a", "b", ["IMG"], web_search=True, call_fn=lambda *a: ("答", 1, 1, ["pxgo.com.tw", "my-best.com"]))
check(res2.searched is False and res2.sources == [], f"沒搜尋：有查網路={res2.searched}")
check(res3.searched is True and res3.sources == ["pxgo.com.tw", "my-best.com"], f"有搜尋：參考網站 {res3.sources}")

def vfake(behaviour: dict, video_behaviour: dict):
    """video_behaviour：影片模式時各模型的結果。"""
    calls = []

    def call_fn(c, keys, system, text, images, search, timeout, video=None):
        calls.append((c.model, "video" if video else ("img" if images else "text")))
        b = (video_behaviour if video else behaviour).get(c.model, "ok")
        if b == "ok":
            return f"答案來自 {c.model}", 1, 1, None
        raise R.CallError(b, "")
    return call_fn, calls


VIDEO = {"id": "abc", "start": 48, "end": 60}
print("9. v3.1 影片模式：Gemini 直接看片段")
r = make_router()
fn, calls = vfake({}, {})
res = r.ask("sys", "有畫面", "沒畫面", [], video=VIDEO, text_video="看影片", call_fn=fn)
check(res.video_used and res.model == "gemini:flash-lite" and calls == [("flash-lite", "video")],
      f"第一個 Gemini 看影片就答出來（{res.model}，呼叫 {calls}）")

print("10. 影片不能看（403，例如不公開影片）＋要求截圖 → 不浪費其他模型，直接回去請網頁截圖")
r = make_router()
fn, calls = vfake({}, {"flash-lite": "403"})
res = r.ask("sys", "a", "b", [], video=VIDEO, text_video="v", stop_for_frames=True, call_fn=fn)
check(res.answer == "" and res.video_failed == "403" and len(calls) == 1, f"只試 1 次就停（{calls}）")
check("gemini:flash-lite" not in r.state.cool and "gemini:flash-lite" not in r.state.no_vision, "沒有把 Gemini 冷卻或標成不能看圖")

print("11. 影片不能看＋手機（不能截圖）→ 所有模型改用文字回答，並標示沒看到畫面")
r = make_router()
fn, calls = vfake({}, {"flash-lite": "400"})
res = r.ask("sys", "a", "b", [], video=VIDEO, text_video="v", stop_for_frames=False, call_fn=fn)
check(res.answer and not res.vision_used and not res.video_used and calls[1] == ("flash-lite", "text"),
      f"改由 {res.model} 用文字回答（{calls[:2]}）")

print("12. 影片模式 503 → 換下一個 Gemini；429 一次 → 換下一個；連續兩次 429 → 停")
r = make_router()
r.cands = [R.Candidate("gemini", "g1", True), R.Candidate("gemini", "g2", True), R.Candidate("gemini", "g3", True)]
fn, calls = vfake({}, {"g1": "503", "g2": "ok"})
res = r.ask("sys", "a", "b", [], video=VIDEO, text_video="v", call_fn=fn)
check(res.model == "gemini:g2" and res.video_used, f"503 後換 g2 看影片成功（{calls}）")
r = make_router()
r.cands = [R.Candidate("gemini", "g1", True), R.Candidate("gemini", "g2", True), R.Candidate("gemini", "g3", True)]
fn, calls = vfake({}, {"g1": "429", "g2": "429"})
res = r.ask("sys", "a", "b", [], video=VIDEO, text_video="v", stop_for_frames=True, call_fn=fn)
check(res.video_failed == "429" and calls == [("g1", "video"), ("g2", "video")], f"連續兩次 429 就停（{calls}）")

print("13. 改用分享畫面的截圖再送一次 → 不再看影片，直接走看圖")
r = make_router()
fn, calls = vfake({}, {})
res = r.ask("sys", "有畫面", "沒畫面", ["IMG"], call_fn=fn)
check(calls[0] == ("flash-lite", "img") and res.vision_used and not res.video_used, f"走看圖（{calls[0]}）")

print("8. Gemini 排序（用 2026-10-12 官方模型清單）")
official = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3-flash-preview", "gemini-3.1-flash-lite",
            "gemini-3.1-flash-live-preview", "gemini-3.1-flash-tts-preview", "gemini-3.5-flash", "gemini-3.5-flash-lite",
            "gemini-3.5-transcribe", "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.8-flash", "gemini-3.8-flash-tts",
            "gemini-3.8-flash-lite-tts", "gemini-3.8-live", "gemini-4-argon", "gemini-2.5-pro", "gemini-3.1-flash-image",
            "gemini-robotics-er-2-preview", "gemini-embedding-2", "gemini-omni-1.1-flash"]
order = R.gemini_order(official)
print("   排序結果：", " → ".join(order))
check(order[0] == "gemini-3.8-flash", "3.8-flash 排第一")
check(order.index("gemini-3.5-flash") < order.index("gemini-3.5-flash-lite"), "同版本 flash 在 flash-lite 前")
check(order.index("gemini-3.1-flash-lite") < order.index("gemini-3-flash-preview") < order.index("gemini-2.5-flash"),
      "版本由新到舊")
check(not any(x in " ".join(order) for x in ("tts", "live", "transcribe", "image", "robotics", "argon", "embedding", "pro")),
      "排除語音、即時、轉錄、圖片、機器人、Gemini 4（免費不提供）、向量、pro")
check([n for n in order if R.gemini_can_search(n)] == ["gemini-2.5-flash", "gemini-2.5-flash-lite"], "只有 2.5 標記為可免費搜尋")

print("\n全部通過 ✅" if ok else "\n有測試失敗 ❌")
