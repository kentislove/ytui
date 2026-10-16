"""雲端 AI 自動切換模組（v2.0）。

開發者規則（2026-10-15）：
  - Gemini、OpenRouter、Groq 三把金鑰，由程式自動挑選可用的免費模型，使用者不用選。
  - 可以慢，但不能沒有答案。
  - 只有「全部模型都試過」且全部遇到 429／503／504／額度用完等錯誤，才算沒有答案。

切換順序：
  第 1 輪：能看圖的模型（跳過冷卻中的）
  第 2 輪：第 1 輪跳過的冷卻中模型也再試一次
  第 3 輪：只能文字的模型，只根據字幕與說明欄回答（會註明沒有看到畫面）
金鑰只從環境變數或 .env 讀取，不會寫進紀錄。
"""
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
STATE_FILE = HERE / "state" / "router_state.json"
ATTEMPT_TIMEOUT = 45          # 單一模型最多等幾秒
GEMINI_MAX_OUT = 4096         # Gemini 輸出上限（含思考）；答案長度由提示詞控制
GEMINI_25_THINK = 512         # Gemini 2.5 思考上限，避免想太久
TOTAL_BUDGET = 300            # 一題最多花幾秒（可以慢，但不無限等）
DISCOVERY_TTL = 6 * 3600      # 模型清單多久重新抓一次

GEMINI = "https://generativelanguage.googleapis.com/v1beta"
OPENROUTER = "https://openrouter.ai/api/v1"
GROQ = "https://api.groq.com/openai/v1"

# 名稱含這些字的模型不是用來對話的（音樂、語音、內容審查、向量、機器人等），排除
EXCLUDE = ("lyria", "tts", "audio", "embedding", "embed", "guard", "safety", "imagen", "veo",
           "image-generation", "-image", "live", "whisper", "orpheus", "playai", "aqa", "learnlm",
           "transcribe", "robotics", "computer-use", "translate", "allam")


def gemini_order(names: list[str]) -> list[str]:
    """Gemini 排序（2026-10-15 依開發者要求修正）：
    版本新的優先（3.8-flash 第一）；同版本 flash 在 flash-lite 前；穩定版在預覽版前。
    只取名稱有 flash 的（gemini-4-argon 等免費版不提供的模型不會被選到）。"""
    def version(n: str) -> float:
        m = re.match(r"gemini-(\d+(?:\.\d+)?)", n)
        return float(m.group(1)) if m else 0.0
    keep = [n for n in names if "flash" in n and not any(x in n for x in EXCLUDE)]
    return sorted(keep, key=lambda n: (-version(n), "lite" in n, "preview" in n, n))


def gemini_can_search(name: str) -> bool:
    """免費版能用 Google 搜尋的只有 gemini-2.5-flash 與 2.5-flash-lite（官方價目頁，每天合計 500 次）。"""
    return name.startswith("gemini-2.5-flash")
# Groq 的清單不標示能不能看圖，用名稱判斷
# 2026-10-15 實測：Groq 已無 Llama 4，改有 qwen/qwen3.8-27b；不支援圖片時程式會自動標記，之後改當文字模型
GROQ_VISION_HINTS = ("llama-4", "vision", "-vl", "scout", "maverick", "qwen3", "gemma")


@dataclass
class Candidate:
    provider: str            # gemini／groq／openrouter
    model: str
    vision: bool
    search: bool = False     # 能用 Google 搜尋佐證（Gemini 2.5）

    @property
    def key(self):
        return f"{self.provider}:{self.model}"


@dataclass
class Attempt:
    model: str
    status: str              # ok／429／503／timeout／...
    secs: float
    detail: str = ""


@dataclass
class Result:
    answer: str = ""
    model: str = ""
    vision_used: bool = True
    video_used: bool = False      # v3.1：Gemini 直接看了影片片段
    video_failed: str = ""        # v3.1：影片模式失敗原因（例如不公開影片、YouTube 每日額度）
    searched: bool = False
    sources: list = field(default_factory=list)
    attempts: list = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0


class CallError(Exception):
    def __init__(self, status: str, detail: str = "", retry_after: float | None = None):
        super().__init__(f"{status} {detail}")
        self.status, self.detail, self.retry_after = status, detail, retry_after


# ---------------- 金鑰 ----------------

def load_keys(env_file: Path = HERE / ".env") -> dict:
    import os
    keys = {k: os.environ.get(k, "").strip() for k in ("GEMINI_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY")}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() in keys and not keys[k.strip()]:
                    keys[k.strip()] = v.strip().strip('"')
    return {k: v for k, v in keys.items() if v and "請貼上" not in v}


# ---------------- HTTP ----------------

def http(method: str, url: str, headers: dict, body: dict | None = None, timeout: float = ATTEMPT_TIMEOUT):
    data = json.dumps(body).encode() if body is not None else None
    # Groq 前面的 Cloudflare 會擋預設的「Python-urllib」名稱（403 error code 1010），所以要帶自己的名稱
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "YouTubeAIHelper/2.0 (+https://kentware.com.tw)", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")[:400]
        ra = e.headers.get("Retry-After")
        raise CallError(str(e.code), text, float(ra) if ra and ra.replace(".", "").isdigit() else None)
    except (TimeoutError, urllib.error.URLError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, TimeoutError) or isinstance(e, TimeoutError) or "timed out" in str(reason):
            raise CallError("timeout", f"超過 {timeout} 秒")
        raise CallError("network", str(reason)[:200])


# ---------------- 模型清單（自動抓最新的） ----------------

def discover(keys: dict) -> list[Candidate]:
    cands: list[Candidate] = []
    if "GEMINI_API_KEY" in keys:
        try:
            data = http("GET", f"{GEMINI}/models?pageSize=200", {"x-goog-api-key": keys["GEMINI_API_KEY"]}, timeout=20)
            names = [m["name"].split("/", 1)[1] for m in data.get("models", [])
                     if "generateContent" in m.get("supportedGenerationMethods", [])]
            cands += [Candidate("gemini", n, True, search=gemini_can_search(n)) for n in gemini_order(names)]
        except CallError:
            pass
    if "GROQ_API_KEY" in keys:
        try:
            data = http("GET", f"{GROQ}/models", {"Authorization": f"Bearer {keys['GROQ_API_KEY']}"}, timeout=20)
            ids = [m["id"] for m in data.get("data", []) if m.get("active", True)]
            ids = [i for i in ids if not any(x in i.lower() for x in EXCLUDE)]
            vis = sorted([i for i in ids if any(h in i.lower() for h in GROQ_VISION_HINTS)], key=lambda i: "maverick" not in i)
            txt = sorted([i for i in ids if i not in vis], key=lambda i: ("70b" not in i and "120b" not in i, i))
            cands += [Candidate("groq", i, True) for i in vis] + [Candidate("groq", i, False) for i in txt]
        except CallError:
            pass
    try:  # OpenRouter 的模型清單是公開的
        data = http("GET", f"{OPENROUTER}/models", {}, timeout=20)
        free = [m for m in data.get("data", [])
                if m.get("pricing", {}).get("prompt") == "0" and m.get("pricing", {}).get("completion") == "0"
                and not any(x in m["id"].lower() for x in EXCLUDE)]
        if "OPENROUTER_API_KEY" in keys:
            vis = [m for m in free if "image" in m.get("architecture", {}).get("input_modalities", [])]
            txt = [m for m in free if m not in vis]
            # 名稱有 google／gemma 的在前；openrouter/free（自動挑選）放最後
            order = lambda m: (m["id"] == "openrouter/free", "gemma" not in m["id"], -m.get("context_length", 0))
            cands += [Candidate("openrouter", m["id"], True) for m in sorted(vis, key=order)]
            cands += [Candidate("openrouter", m["id"], False) for m in sorted(txt, key=order)]
    except CallError:
        pass
    return cands


# ---------------- 呼叫各家 ----------------

def call(c: Candidate, keys: dict, system: str, text: str, images: list[str], search: bool, timeout: float,
         video: dict | None = None):
    """回傳 (答案, 輸入 token, 輸出 token, 參考網站)。參考網站：真的有查網路才是清單，否則 None。
    失敗丟出 CallError。images 為不含前綴的 base64 JPEG。"""
    if c.provider == "gemini":
        parts = [{"text": text}] + [{"inline_data": {"mime_type": "image/jpeg", "data": b}} for b in images]
        if video:   # v3.1：Gemini 直接看 YouTube 網址的片段（含聲音），不用截圖
            parts.insert(0, {"file_data": {"file_uri": f"https://www.youtube.com/watch?v={video['id']}"},
                             "video_metadata": {"start_offset": f"{video['start']}s", "end_offset": f"{video['end']}s"}})
        # v2.1：Gemini 會先「思考」，思考也算在輸出上限內；800 會把答案擠掉（空白或截斷），改 4096
        gen = {"maxOutputTokens": GEMINI_MAX_OUT}
        if c.model.startswith("gemini-2.5"):
            gen["thinkingConfig"] = {"thinkingBudget": GEMINI_25_THINK}
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": gen}
        if search:
            body["tools"] = [{"google_search": {}}]
        d = http("POST", f"{GEMINI}/models/{c.model}:generateContent", {"x-goog-api-key": keys["GEMINI_API_KEY"]}, body, timeout)
        cand = (d.get("candidates") or [{}])[0]
        ans = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
        u = d.get("usageMetadata", {})
        if not ans.strip():
            raise CallError("empty", f"finishReason={cand.get('finishReason')}")
        if cand.get("finishReason") == "MAX_TOKENS":
            raise CallError("empty", "finishReason=MAX_TOKENS（答案被截斷）")
        sources = None
        gm = cand.get("groundingMetadata") or {}
        if search and gm.get("webSearchQueries"):
            sources = []
            for ch in gm.get("groundingChunks", []):
                title = (ch.get("web") or {}).get("title", "").strip()
                if title and title not in sources:
                    sources.append(title)
        return ans, u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0), sources

    base, key = (GROQ, keys["GROQ_API_KEY"]) if c.provider == "groq" else (OPENROUTER, keys["OPENROUTER_API_KEY"])
    content = [{"type": "text", "text": text}] + [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}} for b in images]
    body = {"model": c.model, "max_tokens": 800,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": content if images else text}]}
    headers = {"Authorization": f"Bearer {key}"}
    if c.provider == "openrouter":
        headers |= {"X-Title": "YouTube AI Learning Helper"}
    d = http("POST", f"{base}/chat/completions", headers, body, timeout)
    if "error" in d:   # OpenRouter 有時以 200 回傳錯誤
        err = d["error"]
        raise CallError(str(err.get("code", "error")), str(err.get("message", ""))[:300])
    ans = ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if not ans.strip():
        raise CallError("empty", "沒有內容")
    u = d.get("usage", {})
    return ans, u.get("prompt_tokens", 0), u.get("completion_tokens", 0), None


# ---------------- 冷卻狀態（存檔，重啟後保留） ----------------

class State:
    def __init__(self, path: Path = STATE_FILE):
        self.path = path
        self.cool: dict[str, float] = {}       # 模型 → 冷卻到何時（epoch 秒）
        self.no_vision: set[str] = set()       # 送圖會失敗的模型
        self.dead_provider: dict[str, float] = {}   # 金鑰錯誤的供應商
        if path.exists():
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
                self.cool, self.no_vision = d.get("cool", {}), set(d.get("no_vision", []))
                self.dead_provider = d.get("dead_provider", {})
            except Exception:
                pass

    def save(self):
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps({"cool": self.cool, "no_vision": sorted(self.no_vision),
                                         "dead_provider": self.dead_provider}, ensure_ascii=False, indent=1),
                             encoding="utf-8")

    def cooling(self, k: str) -> bool:
        return self.cool.get(k, 0) > time.time()


def next_utc_midnight() -> float:
    now = datetime.now(timezone.utc)
    return (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0).timestamp()


def classify(e: CallError, c: Candidate, st: State):
    """依錯誤決定冷卻多久；回傳給紀錄看的狀態字串。"""
    s, d = e.status, e.detail.lower()
    now = time.time()
    if s in ("401", "403") and c.provider != "openrouter":
        st.dead_provider[c.provider] = now + 3600
    elif s == "403":   # OpenRouter 個別模型不開放（例如只給開發代理工具用）→ 一週後再看
        st.cool[c.key] = now + 7 * 24 * 3600
    elif s == "404":
        st.cool[c.key] = now + 24 * 3600
    elif s in ("400", "422") and images_unsupported(d):
        st.no_vision.add(c.key)
    elif s == "429" or "quota" in d or "rate" in d:
        daily = any(w in d for w in ("per day", "perday", "daily", "requests per day", "rpd", "free-models-per-day"))
        st.cool[c.key] = next_utc_midnight() if daily else now + (e.retry_after or 60)
    elif s in ("500", "502", "503", "504", "timeout", "network", "empty"):
        st.cool[c.key] = now + 30
    else:
        st.cool[c.key] = now + 120
    return s


def images_unsupported(d: str) -> bool:
    return any(w in d for w in ("image", "vision", "multimodal", "modality", "image_url"))


# ---------------- 主流程 ----------------

class Router:
    def __init__(self):
        self.keys = load_keys()
        self.state = State()
        self.cands: list[Candidate] = []
        self.discovered_at = 0.0

    def candidates(self) -> list[Candidate]:
        if time.time() - self.discovered_at > DISCOVERY_TTL or not self.cands:
            found = discover(self.keys)
            if found:
                self.cands, self.discovered_at = found, time.time()
        return self.cands

    def summary(self) -> dict:
        cs = self.candidates()
        return {"providers": sorted({k.split("_")[0].lower() for k in self.keys}),
                "vision_models": sum(c.vision and c.key not in self.state.no_vision for c in cs),
                "text_models": sum(not c.vision for c in cs),
                "cooling": sum(self.state.cooling(c.key) for c in cs)}

    def ask(self, system: str, text_with_frames: str, text_no_frames: str, images: list[str],
            web_search: bool = False, call_fn=call, video: dict | None = None, text_video: str = "",
            stop_for_frames: bool = False, system_video: str = "") -> Result:
        """v3.1 新增 video={'id','start','end'}：第 0 輪先讓 Gemini 直接看 YouTube 片段。
        影片模式失敗時：stop_for_frames=True 且沒有截圖 → 直接回傳（網頁會請使用者分享畫面再送一次）；
        否則照舊：有截圖走看圖輪，沒截圖就所有模型都用文字回答。"""
        t0 = time.time()
        res = Result()
        cs = self.candidates()
        vision = [c for c in cs if c.vision and c.key not in self.state.no_vision]
        if web_search:  # 要查網路：能搜尋的 Gemini 2.5 排最前面
            vision.sort(key=lambda c: not c.search)
        text_only = [c for c in cs if not c.vision or c.key in self.state.no_vision]
        if not images:   # 沒有截圖：看圖模型也拿來當文字模型用
            text_only = vision + text_only
            vision = []
        tried: set[str] = set()

        def video_round() -> bool:
            gem = [c for c in cs if c.provider == "gemini" and c.vision]
            if web_search:
                gem.sort(key=lambda c: not c.search)
            gem.sort(key=lambda c: self.state.cooling(c.key))   # 沒冷卻的先
            n429 = 0
            for c in gem:
                if time.time() - t0 > TOTAL_BUDGET or c.provider in self.dead_provider_now():
                    return False
                a0 = time.time()
                try:
                    out = call_fn(c, self.keys, system_video or system, text_video, [], web_search and c.search,
                                  min(ATTEMPT_TIMEOUT + 15, max(10, TOTAL_BUDGET - (a0 - t0))), video=video)
                except CallError as e:
                    secs = round(time.time() - a0, 1)
                    if e.status in ("500", "502", "503", "504", "timeout", "network", "empty"):
                        classify(e, c, self.state)          # 暫時性問題：換下一個 Gemini 再試
                        res.attempts.append(Attempt(c.key + "#video", e.status, secs, e.detail[:160]))
                        continue
                    if e.status == "429" and n429 == 0:
                        # 可能只是這個模型的每分鐘限制 → 換下一個 Gemini 試一次（不冷卻）；連續兩次 429 就停
                        n429 += 1
                        res.attempts.append(Attempt(c.key + "#video", e.status, secs, e.detail[:160]))
                        continue
                    # 400／403／404／連續 429：多半是影片本身不能看（不公開、私人、年齡限制）或 YouTube 每日額度，
                    # 換別的 Gemini 也一樣 → 結束影片模式；不冷卻模型，後面看圖／文字還能用它
                    res.attempts.append(Attempt(c.key + "#video", e.status, secs, e.detail[:160]))
                    res.video_failed = e.status
                    return False
                res.attempts.append(Attempt(c.key + "#video", "ok", round(time.time() - a0, 1)))
                ans, tin, tout = out[:3]
                sources = out[3] if len(out) > 3 else None
                res.answer, res.model, res.vision_used, res.video_used = ans.strip(), c.key, True, True
                res.tokens_in, res.tokens_out = tin, tout
                res.searched = web_search and c.search and (sources is not None if len(out) > 3 else True)
                res.sources = sources or []
                self.state.cool.pop(c.key, None)
                return True
            res.video_failed = res.video_failed or "busy"
            return False

        def attempt(c: Candidate, use_images: bool) -> bool:
            if time.time() - t0 > TOTAL_BUDGET:
                if c.key not in tried:
                    res.attempts.append(Attempt(c.key, "budget", 0, f"已超過 {TOTAL_BUDGET} 秒總時限"))
                    tried.add(c.key)
                return False
            if c.provider in self.dead_provider_now():
                if c.key not in tried:
                    res.attempts.append(Attempt(c.key, "key_invalid", 0, "金鑰無效，整家跳過"))
                    tried.add(c.key)
                return False
            tried.add(c.key)
            a0 = time.time()
            remaining = max(10, TOTAL_BUDGET - (a0 - t0))
            try:
                out = call_fn(c, self.keys, system, text_with_frames if use_images else text_no_frames,
                              images if use_images else [], web_search and c.search,
                              min(ATTEMPT_TIMEOUT, remaining))
            except CallError as e:
                status = classify(e, c, self.state)
                res.attempts.append(Attempt(c.key, status, round(time.time() - a0, 1), e.detail[:160]))
                return False
            res.attempts.append(Attempt(c.key, "ok", round(time.time() - a0, 1)))
            ans, tin, tout = out[:3]
            sources = out[3] if len(out) > 3 else None
            res.answer, res.model, res.vision_used = ans.strip(), c.key, use_images
            res.tokens_in, res.tokens_out = tin, tout
            # v2.1：只有模型真的送出搜尋才算「有查網路」
            res.searched = web_search and c.search and (sources is not None if len(out) > 3 else True)
            res.sources = sources or []
            self.state.cool.pop(c.key, None)
            return True

        try:
            # 第 0 輪（v3.1 網頁版）：Gemini 直接看影片片段
            if video:
                if video_round():
                    return res
                if stop_for_frames and not images:
                    return res   # 沒有答案、video_failed 有值 → 網頁改用分享畫面截圖
            # 第 1 輪：能看圖、沒在冷卻的
            for c in vision:
                if not self.state.cooling(c.key) and attempt(c, True):
                    return res
            # 第 2 輪：冷卻中的也試（規則：全部試過才算沒答案）
            for c in vision:
                if c.key not in tried and c.key not in self.state.no_vision and attempt(c, True):
                    return res
            # 第 3 輪：只用文字（字幕＋說明欄）
            for c in text_only:
                if attempt(c, False):
                    return res
            return res   # answer 為空 → 全部失敗
        finally:
            self.state.save()

    def dead_provider_now(self) -> set:
        return {p for p, until in self.state.dead_provider.items() if until > time.time()}
