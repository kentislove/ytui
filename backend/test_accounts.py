"""帳號、額度、紀錄的離線測試（不連網、用暫存資料庫）。用法：.venv\\Scripts\\python.exe test_accounts.py"""
import tempfile
import time

import accounts as A

ok = True
def check(cond, msg):
    global ok
    print(("  ✅ " if cond else "  ❌ ") + msg)
    ok &= cond


def make(limit_users=2, daily=2):
    s = {"GOOGLE_CLIENT_ID": "cid", "ADMIN_EMAILS": {"boss@x.com"}, "COOKIE_PATH": "/", "COOKIE_SECURE": False,
         "FREE_USERS_LIMIT": limit_users, "DAILY_LIMIT": daily, "DATA_DIR": tempfile.mkdtemp()}
    return A.Accounts(s)


def g(sub, email, **kw):
    return {"sub": sub, "email": email, "name": email.split("@")[0], "picture": "", **kw}


print("1. Google 憑證查驗")
good = {"aud": "cid", "iss": "https://accounts.google.com", "email_verified": "true", "exp": str(int(time.time()) + 600),
        "sub": "1", "email": "a@x.com"}
check(A.verify_google("tok" * 10, "cid", fetch=lambda u: good)["email"] == "a@x.com", "正確的憑證通過")
for name, bad in [("別的網站的憑證", {**good, "aud": "other"}), ("email 未驗證", {**good, "email_verified": "false"}),
                  ("已過期", {**good, "exp": "1"}), ("發行者不對", {**good, "iss": "evil.com"})]:
    try:
        A.verify_google("tok" * 10, "cid", fetch=lambda u, b=bad: b)
        check(False, f"{name} 應該被拒絕")
    except A.AuthError as e:
        check(True, f"{name} 被拒絕（{e.message}）")
try:
    A.verify_google("tok" * 10, "", fetch=lambda u: good)
    check(False, "沒設定用戶端 ID 應該被拒絕")
except A.AuthError as e:
    check(e.code == "no_client_id", "沒設定用戶端 ID → 提示後端設定")

check(A.verify_google("tok" * 10, "cid", fetch=lambda u: {**good, "nonce": "n1"}, nonce="n1")["email"] == "a@x.com",
      "v3.2 擴充功能：nonce 一致 → 通過")
try:
    A.verify_google("tok" * 10, "cid", fetch=lambda u: {**good, "nonce": "old"}, nonce="n1")
    check(False, "nonce 不一致應該被拒絕")
except A.AuthError:
    check(True, "v3.2 擴充功能：nonce 不一致（拿舊憑證冒用）→ 拒絕")

print("1b. v3.3 邀請名單")
acc = make()
try:
    acc.login(g("x1", "stranger@x.com"))
    check(False, "沒受邀的人應該登不進來")
except A.AuthError as e:
    check(e.code == "not_invited" and e.status == 403, f"沒受邀 → 拒絕（{e.message[:16]}…）")
check(acc.db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0, "被拒絕的人不會建立帳號、不佔名額")
check(acc.login(g("b0", "BOSS@x.com"))[1]["seq"] == 1, "管理者不用邀請就能登入（Email 大小寫不影響）")
check(acc.add_invite("Friend@X.com ", "同學", "boss@x.com") is True, "加入邀請（自動轉小寫、去空白）")
check(acc.add_invite("friend@x.com", "重複", "boss@x.com") is False, "重複加入同一個 Gmail → 不會重複")
tok, fu = acc.login(g("f0", "friend@x.com"))
check(acc.user_by_token(tok) is not None, "受邀的人可以登入")
check(acc.remove_invite("FRIEND@x.com") is True and acc.user_by_token(tok) is None, "移除邀請 → 對方立刻被登出")
try:
    acc.login(g("f0", "friend@x.com"))
    check(False, "移除後應該登不進來")
except A.AuthError:
    check(True, "移除後再登入 → 拒絕")
check([i["email"] for i in acc.list_invites()] == [], "名單清單正確")

print("1c. v3.3 升級：已經登入過的人自動列入邀請名單")
import sqlite3
d = tempfile.mkdtemp()
old = sqlite3.connect(f"{d}/app.db")
old.executescript("""CREATE TABLE users(id INTEGER PRIMARY KEY, google_sub TEXT UNIQUE NOT NULL, email TEXT NOT NULL, name TEXT,
  picture TEXT, seq INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, last_login TEXT);
  INSERT INTO users(google_sub,email,seq,created_at) VALUES('o1','Old@X.com',1,'2026-10-16');""")
old.commit(); old.close()
up = A.Accounts({**make().s, "DATA_DIR": d})
check(up.is_invited("old@x.com"), "升級前已登入的 Old@X.com 自動在名單上，不會突然被擋")

print("2. 登入建立帳號、記下第幾位、登入憑證")
acc = make()
for e in ("friend@x.com", "late@x.com"):
    acc.add_invite(e, "", "test")
t1, u1 = acc.login(g("s1", "boss@x.com"))
t2, u2 = acc.login(g("s2", "friend@x.com"))
t3, u3 = acc.login(g("s3", "late@x.com"))
check((u1["seq"], u2["seq"], u3["seq"]) == (1, 2, 3), "依登入順序編號 1、2、3")
t2b, u2b = acc.login(g("s2", "friend@x.com"))
check(u2b["seq"] == 2 and u2b["id"] == u2["id"], "同一個人再登入，不會變成新帳號")
check(acc.user_by_token(t2)["email"] == "friend@x.com", "登入憑證可以找到使用者")
check(acc.user_by_token("亂猜的") is None, "亂猜的憑證找不到人")
row = acc.db.execute("SELECT token_hash FROM sessions LIMIT 1").fetchone()[0]
check(len(row) == 64 and row not in (t1, t2, t3), "資料庫只存雜湊值，不存憑證本身")

print("3. 額度")
check(acc.quota(u1)["reason"] == "admin" and acc.reserve(u1) is None, "管理者不限")
check(acc.quota(u3)["reason"] == "full" and acc.reserve(u3)["remaining"] == 0, "第 3 位超過名額（測試設 2 位）→ 不能問")
check(acc.reserve(u2) is None and acc.reserve(u2) is None, "第 2 位今天可以問 2 題")
check(acc.reserve(u2) is not None, "第 3 題被擋")
acc.refund(u2)
check(acc.quota(u2)["remaining"] == 1, "沒有答案時退回 1 題")

print("4. 問答紀錄只看得到自己的")
acc.add_history(u1, {"video_id": "v", "title": "T", "pause": 1, "question": "管理者的題", "answer": "A", "model": "m", "secs": 1})
acc.add_history(u2, {"video_id": "v", "title": "T", "pause": 2, "question": "朋友的題", "answer": "B", "model": "m", "secs": 1})
check([h["question"] for h in acc.list_history(u2)] == ["朋友的題"], "朋友只看到自己的紀錄")
check(acc.clear_history(u2) == 1 and len(acc.list_history(u1)) == 1, "刪除只刪自己的")

print("5. 停用帳號")
acc.set_status(u2["id"], "disabled")
check(acc.user_by_token(t2b) is None, "停用後原本的登入憑證立刻失效")
try:
    acc.login(g("s2", "friend@x.com"))
    check(False, "停用後不能再登入")
except A.AuthError as e:
    check(e.code == "disabled", "停用後再登入被拒絕")
users = acc.list_users()
check([u["admin"] for u in users] == [True, False, False], "管理清單標出管理者")

print("6. 登出")
acc.logout(t1)
check(acc.user_by_token(t1) is None, "登出後憑證失效")

print("\n全部通過 ✅" if ok else "\n有測試失敗 ❌")
