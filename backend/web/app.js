// YouTube AI 學習助手 v3.1 網頁版
// 流程：Google 登入 → 貼網址 → 影片嵌在網頁裡播放 → 暫停提問 → 後端讓 Gemini 直接看「暫停前 12 秒」的片段。
// Gemini 看不了這部影片（不公開、額度用完）時：電腦 → 請使用者「分享這個分頁」，網頁倒回 12 秒截 5 張圖；
// 手機 → 只用標題與說明欄回答。

const I18N = {
  'zh-TW': {
    title: 'YouTube AI 學習助手', logout: '登出', 'theme.to_dark': '切換成夜間（月）', 'theme.to_light': '切換成日間（日）',
    'login.head': '看到哪裡卡住，就停在哪裡問。', 'login.what': '貼上 YouTube 教學影片，暫停後直接提問。AI 會看你停下來之前的十幾秒，告訴你那一步怎麼做。',
    'demo.q': '繩子要從上面還是下面穿？', 'demo.a': '從下面穿過主線，再從左邊的洞拉出來（影片 0:59）。',
    'login.note': '目前是試用期，只有受邀的 Google 帳號能登入。',
    'url.ph': '貼上 YouTube 影片網址', 'url.open': '開啟影片', 'url.bad': '看不懂這個網址，請貼 YouTube 影片網址（例如 https://www.youtube.com/watch?v=…）',
    'player.empty': '貼上網址，影片會在這裡播放',
    'player.err_embed': '這部影片的作者不允許在其他網站播放，請到 YouTube 觀看（電腦可以改用擴充功能）。',
    'player.err_notfound': '找不到這部影片，或影片已被刪除。', 'player.err': '影片無法播放（錯誤 %c%）。',
    'ask.ph': '這一步怎麼做？（按 Enter 送出）', 'ask.mic': '按一下說話', 'ask.mic_stop': '說完了',
    'ask.send': '提問', 'ask.sending': '回答中…', 'ask.web': '允許引用網路資料', 'ask.web_note': '（會附上來源網站）',
    'ask.need_video': '先在上面貼網址開一部影片', 'ask.paused_at': '停在這一秒。AI 會看這之前的 12 秒來回答。',
    'ask.playing_at': '播放中。按「提問」會停在當下這一秒。', 'ask.no_video': '開一部影片，停在不懂的地方再問。',
    'share.how': '按下面的按鈕，在跳出的視窗選「這個分頁」→「分享」。網頁會倒回 12 秒播放並截圖給 AI；畫面只送給 AI，不會錄影。',
    'share.go': '分享這個分頁並重新提問', 'share.skip': '不分享，只用標題回答', 'share.reason': 'AI 這次無法直接看影片：%r%。',
    'share.denied': '沒有分享畫面。可以再按一次，或按「不分享」。', 'share.capturing': '正在倒回截圖給 AI…（%n%/5）',
    'share.wrong': '截到的畫面不對：分享時請選「這個分頁」。', 'share.on': '● 正在分享這個分頁給 AI（關掉分享請按瀏覽器上方的「停止分享」）',
    'answer.title': '回答', 'answer.read': '朗讀', 'answer.stop': '停止', 'answer.frames': 'AI 看到的畫面',
    'answer.disclaimer': 'AI 可能會出錯，重要步驟請以影片為準。',
    'meta.video': 'AI 看了影片片段', 'meta.frames': 'AI 看了 %n% 張截圖', 'meta.text': 'AI 沒看到畫面',
    'meta': '%s% 秒｜%how%｜%m%｜試了 %n% 次', 'meta.searched': '｜有查網路',
    'hist.title': '問過的問題', 'hist.export': '匯出筆記', 'hist.clear': '刪除全部', 'hist.empty': '還沒有問過問題。開一部影片，停在不懂的地方試試看。',
    'hist.confirm': '確定要刪除雲端上你的全部問答紀錄嗎？刪除後無法復原。',
    'admin.title': '管理使用者', 'admin.note': '前 %n% 位每天 %d% 題；要讓朋友試用，請在下方「邀請名單」加入他的 Gmail。',
    'invite.title': '邀請名單', 'invite.note': '只有名單上的 Gmail 能登入。移除後對方會立刻被登出；重複加入同一個 Gmail 不會產生重複。',
    'invite.email_ph': '朋友的 Gmail', 'invite.note_ph': '備註（例如：烘焙班同學）', 'invite.add': '加入',
    'invite.added': '已加入 %e%', 'invite.dup': '%e% 本來就在名單上', 'invite.removed': '已移除 %e%，對方已被登出',
    'invite.confirm': '確定要移除 %e%？對方會立刻被登出，之後不能再登入。', 'invite.remove': '移除',
    'invite.cols': ['Gmail', '備註', '加入時間', '登入過', ''], 'invite.yes': '第 %n% 位', 'invite.no': '還沒登入', 'invite.empty': '名單是空的',
    'admin.cols': ['#', 'Email', '名字', '今日', '總題數', '最後登入', '狀態', ''],
    'admin.disable': '停用', 'admin.enable': '啟用', 'admin.active': '使用中', 'admin.disabled': '已停用', 'admin.me': '管理者',
    'quota.admin': '管理者：不限題數（今天已問 %u% 題）', 'quota.free': '今天還可以問 %r% / %l% 題',
    'quota.full': '試用名額已滿，暫時無法提問', 'health.ok': '雲端 AI 就緒', 'health.bad': '伺服器沒有回應',
    'err.network': '連不到伺服器，請稍後再試', 'err.login': '登入已過期，請重新整理頁面再登入',
    privacy: '你的問題與影片片段會送到 Google、Groq、OpenRouter 的 AI 處理；Google 免費版的內容可能被用於改進其產品。請不要在問題裡寫個人資料。',
  },
  en: {
    title: 'YouTube AI Learning Helper', logout: 'Sign out', 'theme.to_dark': 'Switch to dark mode', 'theme.to_light': 'Switch to light mode',
    'login.head': 'Stuck on a step? Pause right there and ask.', 'login.what': 'Paste a YouTube tutorial, pause where you are stuck and ask. The AI watches the dozen seconds before your pause and explains that step.',
    'demo.q': 'Does the cord go over or under?', 'demo.a': 'Under the core strands, then out through the left loop (video 0:59).',
    'login.note': 'Trial period: only invited Google accounts can sign in.',
    'url.ph': 'Paste a YouTube video URL', 'url.open': 'Open video', 'url.bad': 'That does not look like a YouTube video URL (e.g. https://www.youtube.com/watch?v=…)',
    'player.empty': 'Paste a URL and the video plays here',
    'player.err_embed': 'The owner does not allow this video to play on other sites. Please watch it on YouTube.',
    'player.err_notfound': 'Video not found or removed.', 'player.err': 'The video cannot be played (error %c%).',
    'ask.ph': 'How do I do this step? (Enter to send)', 'ask.mic': 'Tap to talk', 'ask.mic_stop': 'Done',
    'ask.send': 'Ask', 'ask.sending': 'Answering…', 'ask.web': 'Allow web sources', 'ask.web_note': '(source sites are cited)',
    'ask.need_video': 'Paste a URL above to open a video first', 'ask.paused_at': 'Paused here. The AI watches the 12 seconds before this moment.',
    'ask.playing_at': 'Playing. Asking pauses the video at this moment.', 'ask.no_video': 'Open a video and pause where you are stuck.',
    'share.how': 'Press the button and choose "This tab" → "Share". The page rewinds 12 seconds and captures frames for the AI only; nothing is recorded.',
    'share.go': 'Share this tab and ask again', 'share.skip': 'Don\'t share; answer from the title', 'share.reason': 'The AI could not watch the video directly this time: %r%.',
    'share.denied': 'Screen sharing was not started. Try again or choose "Don\'t share".', 'share.capturing': 'Rewinding and capturing for the AI… (%n%/5)',
    'share.wrong': 'Captured the wrong screen: please choose "This tab" when sharing.', 'share.on': '● Sharing this tab with the AI (use the browser\'s "Stop sharing" to end)',
    'answer.title': 'Answer', 'answer.read': 'Read aloud', 'answer.stop': 'Stop', 'answer.frames': 'Frames the AI saw',
    'answer.disclaimer': 'AI can make mistakes; follow the video for important steps.',
    'meta.video': 'AI watched the clip', 'meta.frames': 'AI saw %n% frames', 'meta.text': 'AI did not see the video',
    'meta': '%s% s｜%how%｜%m%｜%n% tries', 'meta.searched': '｜searched the web',
    'hist.title': 'Questions you asked', 'hist.export': 'Export notes', 'hist.clear': 'Delete all', 'hist.empty': 'No questions yet. Open a video and pause where you are stuck.',
    'hist.confirm': 'Delete all your Q&A history in the cloud? This cannot be undone.',
    'admin.title': 'Manage users', 'admin.note': 'The first %n% users get %d% questions a day; to let a friend try it, add their Gmail to the invite list below.',
    'invite.title': 'Invite list', 'invite.note': 'Only listed Gmail accounts can sign in. Removing someone signs them out at once; adding the same Gmail twice has no effect.',
    'invite.email_ph': 'Friend’s Gmail', 'invite.note_ph': 'Note (e.g. baking class)', 'invite.add': 'Add',
    'invite.added': 'Added %e%', 'invite.dup': '%e% is already on the list', 'invite.removed': 'Removed %e% and signed them out',
    'invite.confirm': 'Remove %e%? They will be signed out and cannot sign in again.', 'invite.remove': 'Remove',
    'invite.cols': ['Gmail', 'Note', 'Added', 'Signed in', ''], 'invite.yes': 'user #%n%', 'invite.no': 'not yet', 'invite.empty': 'The list is empty',
    'admin.cols': ['#', 'Email', 'Name', 'Today', 'Total', 'Last sign-in', 'Status', ''],
    'admin.disable': 'Disable', 'admin.enable': 'Enable', 'admin.active': 'Active', 'admin.disabled': 'Disabled', 'admin.me': 'Admin',
    'quota.admin': 'Admin: unlimited (%u% asked today)', 'quota.free': '%r% / %l% questions left today',
    'quota.full': 'Trial seats are full; asking is unavailable', 'health.ok': 'Cloud AI ready', 'health.bad': 'Server not responding',
    'err.network': 'Cannot reach the server; please try again later', 'err.login': 'Your sign-in expired; reload the page and sign in again',
    privacy: 'Your questions and video clips are processed by AI at Google, Groq and OpenRouter; Google may use free-tier content to improve its products. Do not include personal data.',
  },
}

let lang = 'zh-TW'
try { lang = localStorage.getItem('ytai_lang') || (navigator.language.startsWith('zh') ? 'zh-TW' : 'en') } catch {}
const t = (k, p = {}) => {
  let s = (I18N[lang] || I18N['zh-TW'])[k] ?? k
  if (typeof s === 'string') for (const [a, b] of Object.entries(p)) s = s.replace(`%${a}%`, b)
  return s
}
const $ = id => document.getElementById(id)
const show = (id, on) => $(id).classList.toggle('hidden', !on)
const fmt = sec => { const s = Math.max(0, Math.floor(sec || 0)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` }
const sleep = ms => new Promise(r => setTimeout(r, ms))
const CAN_SHARE = !!navigator.mediaDevices?.getDisplayMedia && !/Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent)

function applyLang() {
  document.documentElement.lang = lang
  document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n) })
  document.querySelectorAll('[data-i18n-ph]').forEach(el => { el.placeholder = t(el.dataset.i18nPh) })
  document.querySelectorAll('[data-lang]').forEach(b => b.classList.toggle('on', b.dataset.lang === lang))
  labelTheme()
  if (me) { renderQuota(); renderHistory() }
}
document.querySelectorAll('[data-lang]').forEach(b => b.onclick = () => {
  lang = b.dataset.lang; try { localStorage.setItem('ytai_lang', lang) } catch {}
  applyLang(); if (me?.admin) loadAdmin()
})

// ---------------- 日／月版面 ----------------
const darkQuery = matchMedia('(prefers-color-scheme: dark)')
const currentTheme = () => document.documentElement.dataset.theme || (darkQuery.matches ? 'dark' : 'light')
function labelTheme() {
  $('theme').setAttribute('aria-label', t(currentTheme() === 'dark' ? 'theme.to_light' : 'theme.to_dark'))
  $('theme').title = $('theme').getAttribute('aria-label')
}
$('theme').onclick = () => {
  const next = currentTheme() === 'dark' ? 'light' : 'dark'
  document.documentElement.dataset.theme = next
  try { localStorage.setItem('ytai_theme', next) } catch {}
  labelTheme()
}
darkQuery.addEventListener?.('change', labelTheme)

async function api(path, opt = {}) {
  try {
    const r = await fetch(path, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...opt })
    return { status: r.status, data: await r.json().catch(() => ({})) }
  } catch { return { status: 0, data: { message: t('err.network') } } }
}

// ---------------- 登入 ----------------
let me = null
async function onGoogle(resp) {
  $('login-msg').textContent = ''
  const r = await api('api/auth/google', { method: 'POST', body: JSON.stringify({ credential: resp.credential }) })
  if (r.status === 200) afterLogin(r.data.user)
  else $('login-msg').textContent = r.data.message || 'error'
}
function afterLogin(user) {
  me = user
  show('login-box', false); show('app', true); show('me', true)
  // 大頭貼：Google 圖片主機有時會擋從別的網站來的請求（已設 no-referrer）；還是載不到就顯示名字的第一個字
  $('me-initial').textContent = (me.name || me.email || '?').trim().charAt(0).toUpperCase()
  const avatarFail = () => { show('me-pic', false); show('me-initial', true) }
  $('me-pic').onerror = avatarFail
  if (me.picture) { show('me-initial', false); show('me-pic', true); $('me-pic').src = me.picture } else avatarFail()
  $('me-name').textContent = me.name || me.email
  show('admin-box', !!me.admin)
  renderQuota(); loadHistory(); if (me.admin) loadAdmin()
  const p = new URLSearchParams(location.search)   // 分享連結：?v=影片代碼&t=秒數
  if (p.get('v')) { $('url').value = `https://www.youtube.com/watch?v=${p.get('v')}`; openVideo(p.get('v'), Number(p.get('t')) || 0) }
}
$('logout').onclick = async () => {
  await api('api/auth/logout', { method: 'POST' })
  try { google.accounts.id.disableAutoSelect() } catch {}
  location.href = location.pathname
}
function renderQuota() {
  const q = me.quota, el = $('quota')
  if (q.reason === 'admin') { el.className = 'quota'; el.textContent = t('quota.admin', { u: q.used }) }
  else if (q.reason === 'full') { el.className = 'quota warn'; el.textContent = t('quota.full') }
  else { el.className = 'quota' + (q.remaining ? '' : ' warn'); el.textContent = t('quota.free', { r: q.remaining, l: q.limit }) }
}

// ---------------- 影片播放器（YouTube 官方嵌入） ----------------
let player = null, playerReady = false, videoId = '', pendingSeek = null
window.onYouTubeIframeAPIReady = () => { window.ytApiReady = true }

function parseVideo(text) {
  text = text.trim()
  if (/^[A-Za-z0-9_-]{11}$/.test(text)) return { id: text, t: 0 }
  try {
    const u = new URL(text)
    let id = ''
    if (/(^|\.)youtu\.be$/.test(u.hostname)) id = u.pathname.slice(1, 12)
    else if (/youtube\.com$/.test(u.hostname)) {
      id = u.searchParams.get('v') || (u.pathname.match(/\/(shorts|embed|live)\/([A-Za-z0-9_-]{11})/) || [])[2] || ''
    }
    const tt = u.searchParams.get('t') || ''
    const sec = /^\d+$/.test(tt) ? Number(tt) : ((m => m ? (+m[1] || 0) * 3600 + (+m[2] || 0) * 60 + (+m[3] || 0) : 0)(tt.match(/(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?/)))
    return /^[A-Za-z0-9_-]{11}$/.test(id) ? { id, t: sec } : null
  } catch { return null }
}

async function openVideo(id, start = 0) {
  $('url-msg').textContent = ''
  while (!window.ytApiReady || !window.YT?.Player) await sleep(100)
  show('player-empty', false)
  videoId = id
  const p = new URLSearchParams(location.search); p.set('v', id); p.delete('t')
  history.replaceState(null, '', `${location.pathname}?${p}`)
  if (player && playerReady) { player.loadVideoById({ videoId: id, startSeconds: start }); setTimeout(updateTitle, 1500); return }
  player = new YT.Player('player', {
    videoId: id, playerVars: { playsinline: 1, rel: 0, start: Math.floor(start), hl: lang === 'en' ? 'en' : 'zh-TW' },
    events: {
      onReady: () => { playerReady = true; updateTitle(); if (pendingSeek != null) { player.seekTo(pendingSeek, true); pendingSeek = null } },
      onStateChange: () => { updateTitle(); renderMarks() },
      onError: e => {
        const c = e.data
        $('url-msg').textContent = (c === 101 || c === 150) ? t('player.err_embed') : (c === 100 || c === 2) ? t('player.err_notfound') : t('player.err', { c })
      },
    },
  })
}
function updateTitle() {
  const d = player?.getVideoData?.() || {}
  $('vid-title').textContent = [d.title, d.author].filter(Boolean).join('｜')
}
$('url-form').onsubmit = e => {
  e.preventDefault()
  const v = parseVideo($('url').value)
  if (!v) { $('url-msg').textContent = t('url.bad'); return }
  openVideo(v.id, v.t)
}
function seek(sec) {
  if (!player || !playerReady) { pendingSeek = sec; return }
  player.seekTo(sec, true); player.playVideo()
  $('player-wrap').scrollIntoView({ behavior: 'smooth', block: 'center' })
}
setInterval(() => {   // 作業卡上的大時間：目前暫停／播放在哪一秒
  if (!player || !playerReady || !player.getCurrentTime || !videoId) {
    $('pause-big').textContent = '0:00'; $('pause-at').textContent = t('ask.no_video'); return
  }
  const playing = player.getPlayerState() === YT.PlayerState.PLAYING
  const now = player.getCurrentTime()
  $('pause-big').textContent = fmt(now)
  $('pause-at').textContent = t(playing ? 'ask.playing_at' : 'ask.paused_at')
  document.querySelector('.sheet').classList.toggle('playing', playing)
  const dur = player.getDuration?.() || 0
  if (dur > 0) $('marks-now').style.left = `${Math.min(100, now / dur * 100)}%`
  if (playing && shareStream) bufferFrame()
}, 500)

function renderMarks() {   // 時間軸：這部影片以前問過的題目，在對應秒數標一個薑黃記號
  const box = $('marks')
  box.querySelectorAll('.mark').forEach(m => m.remove())
  const dur = player?.getDuration?.() || 0
  const mine = historyItems.filter(h => h.video_id === videoId)
  show('marks', !!videoId && dur > 0)
  if (!dur) return
  for (const h of mine) {
    const b = document.createElement('button')
    b.className = 'mark'; b.type = 'button'
    b.style.left = `${Math.min(100, h.pause / dur * 100)}%`
    b.title = `${fmt(h.pause)}  ${h.question}`
    b.setAttribute('aria-label', b.title)
    b.onclick = () => { seek(h.pause); setTimeout(() => player.pauseVideo(), 600); showAnswer({ answer: h.answer, time: (h.time || '').replace('T', ' ').slice(0, 16) }) }
    box.append(b)
  }
}

// ---------------- 分享分頁畫面（電腦，Gemini 看不了影片時的備案） ----------------
let shareStream = null, shareVideo = null, ring = [], lastRing = 0
const failedVideos = new Set()

async function ensureShare() {
  if (shareStream?.active) return true
  try {
    shareStream = await navigator.mediaDevices.getDisplayMedia({
      video: { displaySurface: 'browser', frameRate: 5 }, audio: false,
      preferCurrentTab: true, selfBrowserSurface: 'include', surfaceSwitching: 'exclude',
    })
  } catch { return false }
  shareVideo = document.createElement('video')
  shareVideo.muted = true; shareVideo.playsInline = true; shareVideo.srcObject = shareStream
  await shareVideo.play()
  shareStream.getVideoTracks()[0].onended = () => { shareStream = null; ring = []; $('ask-msg').textContent = '' }
  return true
}
function grab() {   // 從分享的分頁畫面切出播放器那一塊
  if (!shareVideo?.videoWidth) return null
  const r = $('player-wrap').getBoundingClientRect()
  const sx = shareVideo.videoWidth / window.innerWidth, sy = shareVideo.videoHeight / window.innerHeight
  const w = Math.min(640, Math.round(r.width * sx)), h = Math.round(w * r.height / r.width)
  const c = document.createElement('canvas'); c.width = w; c.height = h
  c.getContext('2d').drawImage(shareVideo, r.left * sx, r.top * sy, r.width * sx, r.height * sy, 0, 0, w, h)
  return c.toDataURL('image/jpeg', 0.7)
}
function bufferFrame() {   // 分享中、影片播放時，每 3 秒存一張，下次提問就不用倒回
  const now = player.getCurrentTime()
  if (Math.abs(now - lastRing) < 2.8) return
  const d = grab(); if (!d) return
  lastRing = now
  ring = [...ring.filter(f => Math.abs(f.t - now) < 30 && f.t < now), { t: now, data_url: d }].slice(-6)
}
async function captureBack(pause) {
  const fromRing = ring.filter(f => f.t <= pause + 0.5 && f.t >= pause - 14)
  if (fromRing.length >= 4 && pause - fromRing[fromRing.length - 1].t < 2) return fromRing.slice(-5)
  $('player-wrap').scrollIntoView({ block: 'center' }); await sleep(400)
  const wasMuted = player.isMuted(); player.mute()
  const start = Math.max(0, pause - 12), targets = [0, 3, 6, 9, 12].map(x => start + x).filter(x => x <= pause + 0.1)
  const frames = []
  player.seekTo(start, true); player.playVideo()
  const t0 = Date.now()
  while (targets.length && Date.now() - t0 < 30000) {
    await sleep(150)
    const now = player.getCurrentTime()
    if (player.getPlayerState() === YT.PlayerState.PLAYING && now >= targets[0] - 0.15) {
      const d = grab(); if (d) frames.push({ t: now, data_url: d })
      targets.shift()
      $('ask-msg').textContent = t('share.capturing', { n: frames.length })
    }
  }
  player.pauseVideo(); player.seekTo(pause, true)
  if (!wasMuted) player.unMute()
  return frames
}

// ---------------- 提問 ----------------
let lastQuestion = null
async function send(opts = {}) {
  const question = (opts.question ?? $('question').value).trim()
  if (!question) return
  if (!player || !playerReady || !videoId) { $('ask-msg').textContent = t('ask.need_video'); return }
  if (player.getPlayerState() === YT.PlayerState.PLAYING) player.pauseVideo()
  const pause = opts.pause ?? player.getCurrentTime()
  const d = player.getVideoData?.() || {}
  let frames = opts.frames || []
  if (!frames.length && failedVideos.has(videoId) && shareStream?.active) frames = await captureBack(pause)
  lastQuestion = { question, pause }
  $('send').disabled = true; show('share-box', false); $('ask-msg').textContent = t('ask.sending')
  stopSpeaking()
  const body = { video_id: videoId, title: d.title || '', author: d.author || '', pause, question, lang,
                 web_search: $('web-search').checked, can_share: opts.noShare ? false : CAN_SHARE, frames }
  const r = await api('api/ask_video', { method: 'POST', body: JSON.stringify(body) })
  $('send').disabled = false
  if (r.data.quota) { me.quota = r.data.quota; renderQuota() }
  if (r.status === 200) {
    $('ask-msg').textContent = shareStream ? t('share.on') : ''
    showAnswer(r.data, frames)
    $('question').value = ''
    loadHistory()
  } else if (r.status === 409) {   // AI 看不了這部影片 → 請使用者分享畫面
    failedVideos.add(videoId)
    $('ask-msg').textContent = ''
    $('share-reason').textContent = t('share.reason', { r: r.data.message })
    show('share-box', true)
  } else if (r.status === 401) {
    $('ask-msg').textContent = t('err.login')
  } else {
    $('ask-msg').textContent = r.data.message || 'error'
  }
}
$('send').onclick = () => send()
$('question').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send() }
})
$('share-go').onclick = async () => {
  if (!(await ensureShare())) { $('ask-msg').textContent = t('share.denied'); return }
  show('share-box', false)
  const frames = await captureBack(lastQuestion.pause)
  if (!frames.length) { $('ask-msg').textContent = t('share.wrong'); return }
  send({ ...lastQuestion, frames })
}
$('share-skip').onclick = () => { show('share-box', false); send({ ...lastQuestion, noShare: true }) }

function renderAnswer(el, text) {   // 把 m:ss 變成可以點的按鈕（不用 innerHTML，避免插入惡意內容）
  el.textContent = ''
  const re = /(\d{1,2}):([0-5]\d)/g
  let last = 0, m
  while ((m = re.exec(text))) {
    if (m.index > last) el.append(text.slice(last, m.index))
    const b = document.createElement('button'); b.className = 'ts'; b.type = 'button'
    b.textContent = m[0]; const sec = Number(m[1]) * 60 + Number(m[2]); b.onclick = () => seek(sec)
    el.append(b); last = m.index + m[0].length
  }
  if (last < text.length) el.append(text.slice(last))
}
function showAnswer(d, frames = []) {
  show('answer-box', true)
  renderAnswer($('answer'), d.answer)
  if (d.secs != null) {
    const how = d.video_used ? t('meta.video') : d.vision_used ? t('meta.frames', { n: d.frames_used }) : t('meta.text')
    $('answer-meta').textContent = t('meta', { s: d.secs, how, m: (d.model || '').split(':').slice(1).join(':'), n: d.tries })
      + (d.searched ? t('meta.searched') : '')
  } else $('answer-meta').textContent = d.time || ''
  const fb = $('frames'); fb.textContent = ''
  for (const f of frames) {
    const img = document.createElement('img'); img.src = f.data_url; img.title = fmt(f.t); img.onclick = () => seek(f.t)
    fb.append(img)
  }
  show('frames-box', frames.length > 0)
  $('answer-box').scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}

// ---------------- 語音：按一下說話、朗讀（瀏覽器內建，不花錢） ----------------
const SR = window.SpeechRecognition || window.webkitSpeechRecognition
let rec = null
if (SR) show('mic', true)
$('mic').onclick = () => {
  if (rec) { rec.stop(); return }
  rec = new SR(); rec.lang = lang === 'en' ? 'en-US' : 'zh-TW'; rec.interimResults = false
  rec.onresult = e => { $('question').value += e.results[0][0].transcript }
  rec.onend = () => { rec = null; $('mic').querySelector('span').textContent = t('ask.mic') }
  $('mic').querySelector('span').textContent = t('ask.mic_stop')
  if (player && playerReady) player.pauseVideo()
  rec.start()
}
let speaking = false
function stopSpeaking() { speechSynthesis.cancel(); speaking = false; $('speak').querySelector('span').textContent = t('answer.read') }
$('speak').onclick = () => {
  if (speaking) return stopSpeaking()
  const u = new SpeechSynthesisUtterance($('answer').textContent.replace(/【[^】]*】/g, ''))
  u.lang = lang === 'en' ? 'en-US' : 'zh-TW'; u.onend = stopSpeaking
  speechSynthesis.cancel(); speechSynthesis.speak(u); speaking = true
  $('speak').querySelector('span').textContent = t('answer.stop')
}

// ---------------- 問答紀錄（存在雲端） ----------------
let historyItems = []
async function loadHistory() { const r = await api('api/history'); historyItems = r.data.items || []; renderHistory() }
function renderHistory() {
  const ul = $('h-list'); ul.textContent = ''
  show('h-empty', !historyItems.length)
  renderMarks()
  for (const h of historyItems) {
    const li = document.createElement('li'); li.tabIndex = 0
    const tm = document.createElement('span'); tm.className = 'h-time'; tm.textContent = fmt(h.pause)
    const body = document.createElement('div')
    const q = document.createElement('div'); q.className = 'q'; q.textContent = h.question
    const m = document.createElement('div'); m.className = 'h-meta'
    m.textContent = `${h.title || h.video_id}｜${(h.time || '').replace('T', ' ').slice(0, 16)}`
    body.append(q, m)
    li.onkeydown = e => { if (e.key === 'Enter') li.click() }
    li.onclick = async () => {
      if (h.video_id && h.video_id !== 'test') {
        if (h.video_id !== videoId) { await openVideo(h.video_id, h.pause); $('url').value = `https://www.youtube.com/watch?v=${h.video_id}` }
        else seek(h.pause)
        setTimeout(() => player?.pauseVideo?.(), 1200)
      }
      showAnswer({ answer: h.answer, time: (h.time || '').replace('T', ' ').slice(0, 16) })
    }
    li.append(tm, body); ul.append(li)
  }
}
$('h-clear').onclick = async () => { if (confirm(t('hist.confirm'))) { await api('api/history', { method: 'DELETE' }); loadHistory() } }
$('h-export').onclick = () => {
  const lines = [`# ${t('hist.title')}`, '']
  for (const h of historyItems) {
    lines.push(`## ${h.title || h.video_id}（${fmt(h.pause)}）`)
    if (h.video_id && h.video_id !== 'test') lines.push(`https://www.youtube.com/watch?v=${h.video_id}&t=${Math.floor(h.pause)}s`)
    lines.push('', `**Q：** ${h.question}`, '', h.answer, '', `_${h.time}_`, '')
  }
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/markdown' }))
  a.download = `youtube-ai-notes-${new Date().toISOString().slice(0, 10)}.md`
  a.click(); URL.revokeObjectURL(a.href)
}

// ---------------- 管理者 ----------------
async function loadAdmin() {
  const r = await api('api/admin/users')
  if (r.status !== 200) return
  $('admin-note').textContent = t('admin.note', { n: r.data.free_users_limit, d: r.data.daily_limit })
  const tb = $('admin-table'); tb.textContent = ''
  const head = tb.insertRow()
  for (const c of t('admin.cols')) { const th = document.createElement('th'); th.textContent = c; head.append(th) }
  for (const u of r.data.users) {
    const row = tb.insertRow()
    for (const c of [u.seq, u.email, u.name, u.today_used, u.total_questions, (u.last_login || '').replace('T', ' ').slice(0, 16),
      u.admin ? t('admin.me') : t(u.status === 'active' ? 'admin.active' : 'admin.disabled')]) row.insertCell().textContent = c
    const cell = row.insertCell()
    if (!u.admin) {
      const b = document.createElement('button'), next = u.status === 'active' ? 'disabled' : 'active'
      b.textContent = t(next === 'disabled' ? 'admin.disable' : 'admin.enable')
      b.onclick = async () => { await api(`api/admin/users/${u.id}/status`, { method: 'POST', body: JSON.stringify({ status: next }) }); loadAdmin() }
      cell.append(b)
    }
  }
  loadInvites()
}

// ---------------- 邀請名單（v3.3） ----------------
async function loadInvites() {
  const r = await api('api/admin/invites')
  if (r.status !== 200) return
  const tb = $('invite-table'); tb.textContent = ''
  if (!r.data.invites.length) { tb.insertRow().insertCell().textContent = t('invite.empty'); return }
  const head = tb.insertRow()
  for (const c of t('invite.cols')) { const th = document.createElement('th'); th.textContent = c; head.append(th) }
  for (const iv of r.data.invites) {
    const row = tb.insertRow()
    for (const c of [iv.email, iv.note || '', (iv.added_at || '').replace('T', ' ').slice(0, 16),
      iv.seq ? t('invite.yes', { n: iv.seq }) : t('invite.no')]) row.insertCell().textContent = c
    const b = document.createElement('button'); b.className = 'danger'; b.textContent = t('invite.remove')
    b.onclick = async () => {
      if (!confirm(t('invite.confirm', { e: iv.email }))) return
      const d = await api(`api/admin/invites/${encodeURIComponent(iv.email)}`, { method: 'DELETE' })
      $('invite-msg').className = 'msg ' + (d.status === 200 ? 'ok' : 'bad')
      $('invite-msg').textContent = d.status === 200 ? t('invite.removed', { e: iv.email }) : (d.data.message || 'error')
      loadInvites()
    }
    row.insertCell().append(b)
  }
}
$('invite-form').onsubmit = async e => {
  e.preventDefault()
  const email = $('invite-email').value.trim().toLowerCase()
  const r = await api('api/admin/invites', { method: 'POST', body: JSON.stringify({ email, note: $('invite-note').value.trim() }) })
  $('invite-msg').className = 'msg ' + (r.status === 200 ? 'ok' : 'bad')
  if (r.status === 200) {
    $('invite-msg').textContent = t(r.data.added ? 'invite.added' : 'invite.dup', { e: email })
    $('invite-email').value = ''; $('invite-note').value = ''
    loadInvites()
  } else $('invite-msg').textContent = r.data.message || (r.data.detail ? 'Email 格式不對' : 'error')
}

// ---------------- 啟動 ----------------
async function start() {
  applyLang()
  const h = await api('api/health')
  $('health').className = 'health ' + (h.data.ok ? 'ok' : 'bad')
  $('health').textContent = h.data.ok ? t('health.ok') : t('health.bad')
  $('health').title = h.data.version ? `v${h.data.version}` : ''
  const m = await api('api/me')
  if (m.status === 200) return afterLogin(m.data.user)
  const cfg = await api('api/config')
  const init = () => {
    if (!window.google?.accounts?.id) return setTimeout(init, 200)
    google.accounts.id.initialize({ client_id: cfg.data.google_client_id, callback: onGoogle })
    google.accounts.id.renderButton($('gbtn'), { theme: 'outline', size: 'large', locale: lang === 'en' ? 'en' : 'zh-TW' })
  }
  init()
}
start()
