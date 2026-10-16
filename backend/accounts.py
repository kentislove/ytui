"""帳號、登入憑證、每日額度、問答紀錄（v3.0）。

資料庫：SQLite（一個檔案 data/app.db），NAS 上掛載到容器外，重建容器不會不見。
登入：前端用 Google 登入拿到「ID 憑證」→ 後端向 Google 查驗（tokeninfo，免費）→
      發自己的登入憑證（隨機 43 字元），資料庫只存它的 SHA-256 雜湊值。
試用名單：由 Google Cloud「測試使用者」控管（不在名單上的人在 Google 那一關就登不進來）。
額度：註冊順序前 FREE_USERS_LIMIT 位每天 DAILY_LIMIT 題（台灣時間 0 點重算）；管理者不限。
"""
import hashlib
import json
import os
import secrets
import sqlite3
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
TW = timezone(timedelta(hours=8))
SESSION_DAYS = 30
GOOGLE_ISS = ("accounts.google.com", "https://accounts.google.com")


def load_settings(env_file: Path = HERE / ".env") -> dict:
    """設定值：環境變數優先（Docker），其次 .env。金鑰不在這裡讀。"""
    defaults = {"GOOGLE_CLIENT_ID": "", "ADMIN_EMAILS": "", "COOKIE_PATH": "/", "COOKIE_SECURE": "0",
                "FREE_USERS_LIMIT": "50", "DAILY_LIMIT": "5", "DATA_DIR": str(HERE / "data")}
    s = {k: os.environ.get(k, "").strip() for k in defaults}   # strip：去掉 Windows 換行留下的 \r
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = (x.strip() for x in line.split("=", 1))
                if k in s and not s[k]:
                    s[k] = v.strip('"')
    s = {k: (s[k] or v) for k, v in defaults.items()}
    s["ADMIN_EMAILS"] = {e.strip().lower() for e in s["ADMIN_EMAILS"].split(",") if e.strip()}
    s["COOKIE_SECURE"] = s["COOKIE_SECURE"] == "1"
    s["FREE_USERS_LIMIT"], s["DAILY_LIMIT"] = int(s["FREE_USERS_LIMIT"]), int(s["DAILY_LIMIT"])
    return s


class AuthError(Exception):
    def __init__(self, code: str, message: str, status: int = 401):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def verify_google(id_token: str, client_id: str, fetch=None, nonce: str = "") -> dict:
    """向 Google 查驗 ID 憑證。fetch 供離線測試替換。
    nonce：擴充功能登入時自己產生的一次性亂碼；有給就必須跟憑證裡的一致（防止別人拿舊憑證來冒用）。"""
    if not client_id:
        raise AuthError("no_client_id", "後端還沒設定 GOOGLE_CLIENT_ID", 500)
    url = "https://oauth2.googleapis.com/tokeninfo?" + urllib.parse.urlencode({"id_token": id_token})
    try:
        info = fetch(url) if fetch else json.loads(urllib.request.urlopen(url, timeout=10).read().decode("utf-8"))
    except Exception:
        raise AuthError("google_rejected", "Google 登入驗證失敗，請重新登入")
    if info.get("aud") != client_id or info.get("iss") not in GOOGLE_ISS:
        raise AuthError("google_rejected", "登入憑證不是這個網站的")
    if str(info.get("email_verified")).lower() != "true":
        raise AuthError("email_unverified", "這個 Google 帳號的 email 尚未驗證")
    if int(info.get("exp", 0)) < datetime.now(timezone.utc).timestamp():
        raise AuthError("expired", "登入憑證已過期，請重新登入")
    if nonce and info.get("nonce") != nonce:
        raise AuthError("google_rejected", "登入憑證不是這次登入產生的，請重新登入")
    return info


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def now_iso() -> str:
    return datetime.now(TW).isoformat(timespec="seconds")


def today() -> str:
    return datetime.now(TW).strftime("%Y-%m-%d")


class Accounts:
    def __init__(self, settings: dict):
        self.s = settings
        Path(settings["DATA_DIR"]).mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(Path(settings["DATA_DIR"]) / "app.db", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock, self.db:
            self.db.executescript("""
            CREATE TABLE IF NOT EXISTS users(
              id INTEGER PRIMARY KEY, google_sub TEXT UNIQUE NOT NULL, email TEXT NOT NULL, name TEXT,
              picture TEXT, seq INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active',
              created_at TEXT NOT NULL, last_login TEXT);
            CREATE TABLE IF NOT EXISTS sessions(
              token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS usage(
              user_id INTEGER NOT NULL, day TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id, day));
            CREATE TABLE IF NOT EXISTS history(
              id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, time TEXT NOT NULL, video_id TEXT, title TEXT,
              pause REAL, question TEXT, answer TEXT, model TEXT, secs REAL);
            CREATE INDEX IF NOT EXISTS history_user ON history(user_id, id);
            CREATE TABLE IF NOT EXISTS invites(
              email TEXT PRIMARY KEY, note TEXT, added_by TEXT, added_at TEXT NOT NULL);
            """)
            # v3.3 第一次啟動：已經登入過的人自動列入邀請名單，升級後不會突然被擋
            if not self.db.execute("SELECT COUNT(*) FROM invites").fetchone()[0]:
                for (email,) in self.db.execute("SELECT lower(email) FROM users").fetchall():
                    if email not in settings["ADMIN_EMAILS"]:   # 管理者本來就能登入，不用列
                        self.db.execute("INSERT OR IGNORE INTO invites(email,note,added_by,added_at) "
                                        "VALUES(?,'v3.3 升級前已登入','system',?)", (email, now_iso()))

    # ---------- 邀請名單（v3.3） ----------
    # Google 的「測試使用者」名單對只要求基本身分（openid、email、profile）的網站無效，
    # 所以由我們自己控管：管理者一律可以登入，其他人必須在邀請名單上。
    def is_invited(self, email: str) -> bool:
        email = (email or "").strip().lower()
        if email in self.s["ADMIN_EMAILS"]:
            return True
        with self.lock:
            return self.db.execute("SELECT 1 FROM invites WHERE email=?", (email,)).fetchone() is not None

    def list_invites(self) -> list[dict]:
        with self.lock:
            rows = self.db.execute("""SELECT i.email, i.note, i.added_by, i.added_at,
                   (SELECT seq FROM users u WHERE lower(u.email)=i.email) AS seq,
                   (SELECT last_login FROM users u WHERE lower(u.email)=i.email) AS last_login
                   FROM invites i ORDER BY i.added_at DESC""").fetchall()
        return [dict(r) for r in rows]

    def add_invite(self, email: str, note: str, by: str) -> bool:
        """回傳 True＝新加入；False＝本來就在名單上（不會重複）。"""
        with self.lock, self.db:
            cur = self.db.execute("INSERT OR IGNORE INTO invites(email,note,added_by,added_at) VALUES(?,?,?,?)",
                                  (email.strip().lower(), note.strip(), by, now_iso()))
            return cur.rowcount == 1

    def remove_invite(self, email: str) -> bool:
        """移除邀請；那個人目前的登入憑證也一併作廢（立刻登出）。"""
        email = email.strip().lower()
        with self.lock, self.db:
            n = self.db.execute("DELETE FROM invites WHERE email=?", (email,)).rowcount
            self.db.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE lower(email)=?)", (email,))
            return n == 1

    # ---------- 登入 ----------
    def login(self, info: dict) -> tuple[str, dict]:
        """Google 查驗通過後呼叫：沒有帳號就建立（記下第幾位），回傳 (登入憑證, 使用者)。
        v3.3：不在邀請名單上的人直接拒絕，而且不建立帳號、不佔用名額。"""
        if not self.is_invited(info.get("email", "")):
            raise AuthError("not_invited", "這個 Google 帳號尚未受邀。目前是試用期，請聯絡管理者把你的 Gmail 加入邀請名單。", 403)
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM users WHERE google_sub=?", (info["sub"],)).fetchone()
            if row is None:
                seq = self.db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM users").fetchone()[0]
                self.db.execute("INSERT INTO users(google_sub,email,name,picture,seq,created_at,last_login) "
                                "VALUES(?,?,?,?,?,?,?)", (info["sub"], info.get("email", ""), info.get("name", ""),
                                                         info.get("picture", ""), seq, now_iso(), now_iso()))
            else:
                self.db.execute("UPDATE users SET email=?, name=?, picture=?, last_login=? WHERE id=?",
                                (info.get("email", ""), info.get("name", ""), info.get("picture", ""), now_iso(), row["id"]))
            user = self.db.execute("SELECT * FROM users WHERE google_sub=?", (info["sub"],)).fetchone()
            if user["status"] != "active":
                raise AuthError("disabled", "這個帳號已被停用", 403)
            token = secrets.token_urlsafe(32)
            expires = (datetime.now(TW) + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
            self.db.execute("INSERT INTO sessions VALUES(?,?,?,?)", (_hash(token), user["id"], now_iso(), expires))
        return token, dict(user)

    def user_by_token(self, token: str | None) -> dict | None:
        if not token:
            return None
        with self.lock:
            row = self.db.execute("SELECT u.*, s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id "
                                  "WHERE s.token_hash=?", (_hash(token),)).fetchone()
        if row is None or row["expires_at"] < now_iso() or row["status"] != "active":
            return None
        if not self.is_invited(row["email"]):   # v3.3：邀請被移除 → 立刻失效
            return None
        return dict(row)

    def logout(self, token: str | None):
        if token:
            with self.lock, self.db:
                self.db.execute("DELETE FROM sessions WHERE token_hash=?", (_hash(token),))

    # ---------- 角色與額度 ----------
    def is_admin(self, user: dict) -> bool:
        return user["email"].lower() in self.s["ADMIN_EMAILS"]

    def quota(self, user: dict) -> dict:
        with self.lock:
            return self._quota_nolock(user)

    def _quota_nolock(self, user: dict) -> dict:
        """回傳 {limit, used, remaining, reason}；limit=None 代表不限。呼叫前要先拿到 self.lock。"""
        r = self.db.execute("SELECT count FROM usage WHERE user_id=? AND day=?", (user["id"], today())).fetchone()
        used = r["count"] if r else 0
        if self.is_admin(user):
            return {"limit": None, "used": used, "remaining": None, "reason": "admin"}
        if user["seq"] > self.s["FREE_USERS_LIMIT"]:
            return {"limit": 0, "used": used, "remaining": 0, "reason": "full"}
        limit = self.s["DAILY_LIMIT"]
        return {"limit": limit, "used": used, "remaining": max(0, limit - used), "reason": "free"}

    def reserve(self, user: dict) -> dict | None:
        """提問前先扣 1 題（同時送出多題也不會超過額度）。額度不足回傳 quota，成功回傳 None。"""
        with self.lock, self.db:
            q = self._quota_nolock(user)
            if q["remaining"] is not None and q["remaining"] <= 0:
                return q
            self.db.execute("INSERT INTO usage(user_id,day,count) VALUES(?,?,1) "
                            "ON CONFLICT(user_id,day) DO UPDATE SET count=count+1", (user["id"], today()))
        return None

    def refund(self, user: dict):
        """所有模型都失敗、沒有答案 → 退回預扣的 1 題。"""
        with self.lock, self.db:
            self.db.execute("UPDATE usage SET count=MAX(0,count-1) WHERE user_id=? AND day=?", (user["id"], today()))

    # ---------- 問答紀錄 ----------
    def add_history(self, user: dict, item: dict) -> int:
        with self.lock, self.db:
            cur = self.db.execute("INSERT INTO history(user_id,time,video_id,title,pause,question,answer,model,secs) "
                                  "VALUES(?,?,?,?,?,?,?,?,?)",
                                  (user["id"], now_iso(), item["video_id"], item["title"], item["pause"],
                                   item["question"], item["answer"], item["model"], item["secs"]))
            return cur.lastrowid

    def list_history(self, user: dict, limit: int = 500) -> list[dict]:
        with self.lock:
            rows = self.db.execute("SELECT id,time,video_id,title,pause,question,answer,model,secs FROM history "
                                   "WHERE user_id=? ORDER BY id DESC LIMIT ?", (user["id"], limit)).fetchall()
        return [dict(r) for r in rows]

    def clear_history(self, user: dict) -> int:
        with self.lock, self.db:
            return self.db.execute("DELETE FROM history WHERE user_id=?", (user["id"],)).rowcount

    # ---------- 管理者 ----------
    def list_users(self) -> list[dict]:
        with self.lock:
            rows = self.db.execute("""SELECT u.id,u.email,u.name,u.seq,u.status,u.created_at,u.last_login,
                   COALESCE((SELECT count FROM usage WHERE user_id=u.id AND day=?),0) AS today_used,
                   (SELECT COUNT(*) FROM history WHERE user_id=u.id) AS total_questions
                   FROM users u ORDER BY u.seq""", (today(),)).fetchall()
        return [dict(r) | {"admin": r["email"].lower() in self.s["ADMIN_EMAILS"]} for r in rows]

    def set_status(self, user_id: int, status: str):
        with self.lock, self.db:
            self.db.execute("UPDATE users SET status=? WHERE id=?", (status, user_id))
            if status != "active":
                self.db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
