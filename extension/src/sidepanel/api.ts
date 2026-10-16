// 側邊欄與「YouTube 分頁」「後端」的溝通。
// v3.2：後端改成跟網頁版同一個（NAS 或本機測試），用同一個 Google 帳號登入，問答紀錄存在後端。
export const BACKENDS = {
  nas: 'https://your-server.example.com/ytai/',   // ← 改成你自己的後端網址（結尾要有 /）
  local: 'http://localhost:5173/',
} as const
export type BackendKey = keyof typeof BACKENDS
export const VERSION = chrome.runtime.getManifest().version

export interface Frame { t: number; data_url: string }
export interface Subtitle { start: number; end: number; text: string }
export interface Capture {
  error?: string
  videoId: string
  title: string
  author: string
  description: string
  captionLangs: string[]
  pause: number
  frames: Frame[]
  subtitles: Subtitle[]
  subtitleSource: string
  subtitleTotal: number
  diag: Record<string, unknown>
}
export interface Ping {
  ok: boolean; videoId: string | null; title: string; ad: boolean; t: number; paused: boolean
  subtitleCount: number; subtitleSource: string
}
export interface Health {
  ok: boolean; version?: string; min_extension?: string
  vision_models?: number; text_models?: number; gpu_message?: string | null
}
export interface Quota { limit: number | null; used: number; remaining: number | null; reason: string }
export interface User { email: string; name: string; picture: string; seq: number; admin: boolean; quota: Quota }
export interface HistoryItem {
  id: number; time: string; video_id: string; title: string; pause: number
  question: string; answer: string; model: string; secs: number
}
export interface AskResult {
  answer?: string; secs?: number; frames_used?: number; had_subtitles?: boolean
  warning?: string | null; error?: string; message?: string
  model?: string; tries?: number; vision_used?: boolean; searched?: boolean; quota?: Quota
}

// ---------- 設定：用哪個後端、登入憑證 ----------
let backendKey: BackendKey = 'nas'
let token = ''
export async function loadConnection(): Promise<BackendKey> {
  const s = await chrome.storage.local.get({ backend: 'nas', token: '' })
  backendKey = (s.backend in BACKENDS ? s.backend : 'nas') as BackendKey
  token = s.token
  return backendKey
}
export async function setBackend(k: BackendKey) {
  backendKey = k; token = ''   // 換後端就要重新登入（不同後端是不同的帳號資料庫）
  await chrome.storage.local.set({ backend: k, token: '' })
}
export const backendUrl = () => BACKENDS[backendKey]
export const hasToken = () => !!token

async function call<T>(path: string, opt: RequestInit = {}): Promise<{ status: number; data: T & { error?: string; message?: string } }> {
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers.Authorization = `Bearer ${token}`
    const r = await fetch(backendUrl() + path, { ...opt, headers })
    const data = await r.json().catch(() => ({}))
    if (r.status === 401 && token) { token = ''; await chrome.storage.local.set({ token: '' }) }
    return { status: r.status, data }
  } catch {
    return { status: 0, data: { error: 'network' } as any }
  }
}

export async function health(): Promise<Health | null> {
  const r = await call<Health>('api/health')
  return r.status === 200 ? r.data : null
}
export async function me(): Promise<User | null> {
  if (!token) return null
  const r = await call<{ user: User }>('api/me')
  return r.status === 200 ? r.data.user : null
}

/** Google 登入：開 Google 的登入視窗 → 拿到 ID 憑證 → 交給後端換成這套系統的登入憑證。 */
export async function login(): Promise<{ user?: User; error?: string }> {
  const cfg = await call<{ google_client_id: string }>('api/config')
  if (cfg.status !== 200 || !cfg.data.google_client_id) return { error: 'network' }
  const nonce = crypto.randomUUID()
  const url = 'https://accounts.google.com/o/oauth2/v2/auth?' + new URLSearchParams({
    client_id: cfg.data.google_client_id, response_type: 'id_token', redirect_uri: chrome.identity.getRedirectURL(),
    scope: 'openid email profile', nonce, prompt: 'select_account',
  })
  let back = ''
  try {
    back = await chrome.identity.launchWebAuthFlow({ url, interactive: true }) || ''
  } catch (e) {
    return { error: String((e as Error).message || e) }   // 使用者關掉視窗，或 Google 拒絕
  }
  const idToken = new URLSearchParams(back.split('#')[1] || '').get('id_token')
  if (!idToken) return { error: new URLSearchParams(back.split('#')[1] || back.split('?')[1] || '').get('error') || 'no_token' }
  const r = await call<{ user: User; token: string }>('api/auth/google', {
    method: 'POST', body: JSON.stringify({ credential: idToken, nonce }),
  })
  if (r.status !== 200) return { error: r.data.message || 'login_failed' }
  token = r.data.token
  await chrome.storage.local.set({ token })
  return { user: r.data.user }
}
export async function logout() {
  await call('api/auth/logout', { method: 'POST' })
  token = ''
  await chrome.storage.local.set({ token: '' })
}

export async function ask(cap: Capture, question: string, lang: string, webSearch = false): Promise<AskResult & { status: number }> {
  const body = {
    video_id: cap.videoId, title: cap.title, author: cap.author, description: cap.description,
    pause: cap.pause, question, frames: cap.frames, subtitles: cap.subtitles, lang, web_search: webSearch,
    subtitle_source: cap.subtitleSource, subtitle_total: cap.subtitleTotal, diag: cap.diag || {},
  }
  const r = await call<AskResult>('api/ask', { method: 'POST', body: JSON.stringify(body) })
  return { ...r.data, status: r.status }
}
export async function history(): Promise<HistoryItem[]> {
  const r = await call<{ items: HistoryItem[] }>('api/history')
  return r.status === 200 ? r.data.items : []
}
export async function clearHistory() { await call('api/history', { method: 'DELETE' }) }

/** 版本比較：a < b 回傳 true（例如 0.3.1 < 0.3.2）。 */
export function older(a: string, b: string) {
  const pa = a.split('.').map(Number), pb = b.split('.').map(Number)
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) < (pb[i] || 0)
  }
  return false
}

export async function activeYoutubeTab(): Promise<any | null> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  if (!tab || !tab.url || !/^https:\/\/www\.youtube\.com\/watch/.test(tab.url)) return null
  return tab
}

export async function sendToTab<T>(tabId: number, msg: object): Promise<T | null> {
  try {
    return await chrome.tabs.sendMessage(tabId, msg)
  } catch {
    return null // 頁面還沒載入擴充功能的腳本（例如安裝前就開著的分頁）
  }
}

// 把回答中的 m:ss 時間點拆出來，讓畫面變成可以點的按鈕（不用 v-html，避免插入惡意內容）
export type Part = { text: string } | { label: string; t: number }
export function splitTimestamps(text: string): Part[] {
  const parts: Part[] = []
  const re = /(\d{1,2}):([0-5]\d)/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push({ text: text.slice(last, m.index) })
    parts.push({ label: m[0], t: Number(m[1]) * 60 + Number(m[2]) })
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push({ text: text.slice(last) })
  return parts
}

export const fmt = (sec: number) => {
  const s = Math.max(0, Math.floor(sec))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
