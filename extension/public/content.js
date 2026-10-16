// 在 YouTube 頁面執行（擴充功能的隔離環境）：暫存畫面、整理字幕、回應側邊欄的請求。
// 規格（第 0 階段決策）：暫停點前 12、9、6、3 秒＋當下，共 5 張；不往後跳；播廣告時一律不截圖。
(() => {
  const FRAME_STEP = 3
  const FRAME_COUNT = 5
  const MAX_WIDTH = 854
  const SUB_RANGE = 120 // 只送暫停點前後 120 秒內的字幕

  const state = {
    videoId: null,
    frames: [],          // 播放時每 3 秒暫存一張，只留最近幾張，存在這台電腦的記憶體
    trackSubs: [],       // 播放器下載的字幕檔（完整）
    screenSubs: [],      // 從畫面上的 CC 文字讀到的字幕（備援）
    lastCapT: -99,
  }

  const video = () => document.querySelector('#movie_player video') || document.querySelector('video')
  const player = () => document.querySelector('#movie_player')
  const isAd = () => !!(player() && player().classList.contains('ad-showing'))
  const currentVideoId = () => new URL(location.href).searchParams.get('v')

  // ---------- 和 main_world.js 溝通 ----------
  const pending = {}
  let seq = 0
  const askMain = (type, extra = {}, timeout = 1500) => new Promise((resolve) => {
    const id = ++seq
    pending[id] = resolve
    window.postMessage(Object.assign({ source: 'ytai-content', type, id }, extra), '*')
    setTimeout(() => { if (pending[id]) { delete pending[id]; resolve(null) } }, timeout)
  })

  window.addEventListener('message', (e) => {
    if (e.source !== window || !e.data || e.data.source !== 'ytai-main') return
    const { type, payload } = e.data
    if (type === 'TIMEDTEXT') return parseTimedText(payload)
    if (payload && pending[payload.id]) { pending[payload.id](payload); delete pending[payload.id] }
  })

  function parseTimedText({ url, body }) {
    try {
      const vid = new URL(url, location.href).searchParams.get('v')
      if (vid && vid !== currentVideoId()) return
    } catch (e) {}
    const lines = []
    try {
      const j = JSON.parse(body)
      for (const ev of j.events || []) {
        if (!ev.segs) continue
        const text = ev.segs.map((s) => s.utf8 || '').join('').replace(/\s*\n\s*/g, ' ').trim()
        if (text) lines.push({ start: ev.tStartMs / 1000, end: (ev.tStartMs + (ev.dDurationMs || 0)) / 1000, text })
      }
    } catch (e) {
      // XML 格式字幕。YouTube 頁面啟用 Trusted Types，不能用 DOMParser，改用文字比對解析。
      const attr = (tag, name) => { const m = tag.match(new RegExp(`\\b${name}="([\\d.]+)"`)); return m ? Number(m[1]) : NaN }
      const decode = (s) => s.replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/\s+/g, ' ').trim()
      for (const m of body.matchAll(/<(p|text)\b([^>]*)>([\s\S]*?)<\/\1>/g)) {
        const ms = m[1] === 'p' ? attr(m[2], 't') : attr(m[2], 'start') * 1000
        const dur = m[1] === 'p' ? attr(m[2], 'd') : attr(m[2], 'dur') * 1000
        const text = decode(m[3])
        if (text && !isNaN(ms)) lines.push({ start: ms / 1000, end: (ms + (dur || 0)) / 1000, text })
      }
    }
    if (lines.length) state.trackSubs = lines
  }

  // v1.2：向 main_world.js 拿快取的字幕（播放器在本程式就緒前就下載的那份）
  async function pullCachedSubs() {
    if (state.trackSubs.length) return
    const r = await askMain('GET_TIMEDTEXT', { videoId: currentVideoId() })
    if (r && r.body) parseTimedText(r)
  }

  // ---------- 換影片時清空 ----------
  function resetIfNewVideo() {
    const id = currentVideoId()
    if (id === state.videoId) return
    state.videoId = id
    state.frames = []
    state.trackSubs = []
    state.screenSubs = []
    state.lastCapT = -99
    if (id) {
      setTimeout(pullCachedSubs, 1000)
      setTimeout(maybeEnableCaptions, 3000)
      setTimeout(pullCachedSubs, 6000)
    }
  }

  function maybeEnableCaptions() {
    chrome.storage.local.get({ autoCaptions: true }, ({ autoCaptions }) => {
      if (autoCaptions && !state.trackSubs.length) askMain('ENABLE_CAPTIONS')
    })
  }

  // ---------- 截圖 ----------
  function grab(v) {
    const w = Math.min(MAX_WIDTH, v.videoWidth)
    const h = Math.round((v.videoHeight * w) / v.videoWidth)
    const c = document.createElement('canvas')
    c.width = w
    c.height = h
    c.getContext('2d').drawImage(v, 0, 0, w, h)
    return c.toDataURL('image/jpeg', 0.85)
  }

  // 每秒檢查一次：播放中、非廣告時，影片每前進 3 秒暫存一張
  setInterval(() => {
    resetIfNewVideo()
    const v = video()
    if (!v || v.readyState < 2 || !v.videoWidth || isAd()) return
    const t = v.currentTime

    // 備援字幕：讀畫面上正在顯示的 CC 文字
    const txt = [...document.querySelectorAll('.ytp-caption-segment')].map((e) => e.textContent).join(' ').trim()
    const last = state.screenSubs[state.screenSubs.length - 1]
    if (txt && (!last || last.text !== txt)) state.screenSubs.push({ start: t, end: t, text: txt })
    if (state.screenSubs.length > 800) state.screenSubs.shift()

    if (v.paused) return
    if (Math.abs(t - state.lastCapT) > FRAME_STEP * 3) state.frames = [] // 使用者拖動了進度條
    if (t - state.lastCapT >= FRAME_STEP || t < state.lastCapT) {
      try {
        state.frames.push({ t, data_url: grab(v) })
        state.lastCapT = t
      } catch (e) {}
      state.frames = state.frames.filter((f) => f.t > t - 15 && f.t <= t + 0.5).slice(-6)
    }
  }, 1000)

  const seekTo = (v, t) => new Promise((resolve) => {
    const done = () => { clearTimeout(timer); resolve() }
    const timer = setTimeout(done, 4000) // 插播廣告時 seeked 不會觸發，最多等 4 秒
    v.addEventListener('seeked', done, { once: true })
    v.currentTime = t
  })

  async function capture() {
    resetIfNewVideo()
    const v = video()
    if (!v || !v.videoWidth) return { error: 'NO_VIDEO' }
    if (isAd()) return { error: 'AD' }

    v.pause()
    const pause = v.currentTime
    const targets = []
    for (let i = FRAME_COUNT - 1; i >= 1; i--) if (pause - FRAME_STEP * i >= 0) targets.push(pause - FRAME_STEP * i)

    const now = grab(v)
    const frames = []
    const missing = []
    for (const t of targets) {
      const f = state.frames.find((f) => Math.abs(f.t - t) <= 1.6 && f.t < pause - 0.5)
      if (f) frames.push({ t: f.t, data_url: f.data_url })
      else missing.push(t)
    }
    // 沒有暫存（例如剛拖動進度條就暫停）：往回跳補截，再回到暫停點
    if (missing.length) {
      for (const t of missing) {
        await seekTo(v, t)
        await new Promise((r) => setTimeout(r, 250))
        if (isAd()) break
        try { frames.push({ t, data_url: grab(v) }) } catch (e) {}
      }
      await seekTo(v, pause)
    }
    frames.push({ t: pause, data_url: now })
    frames.sort((a, b) => a.t - b.t)

    const meta = (await askMain('GET_META')) || {}
    await pullCachedSubs()
    const diag = await diagnose()
    const { list, source } = currentSubs()
    const subtitleTotal = list.length
    const subtitles = list.filter((s) => s.start >= pause - SUB_RANGE && s.start <= pause + SUB_RANGE)
    const subtitleSource = source

    return {
      videoId: currentVideoId(),
      title: meta.title || document.title.replace(/ - YouTube$/, ''),
      author: meta.author || '',
      description: meta.description || '',
      captionLangs: meta.captionLangs || [],
      pause,
      frames,
      subtitles,
      subtitleSource,
      subtitleTotal,
      diag,
    }
  }

  // v1.2：診斷資訊（main_world.js 的攔截統計＋本程式的字幕狀態）
  async function diagnose() {
    const d = (await askMain('GET_DIAG')) || { mainWorld: 'no response' }
    delete d.id
    return Object.assign(d, { trackSubs: state.trackSubs.length, screenSubs: state.screenSubs.length })
  }

  // 字幕檔（完整）優先，沒有才用畫面上讀到的 CC 文字
  function currentSubs() {
    if (state.trackSubs.length) return { list: state.trackSubs, source: 'track' }
    if (state.screenSubs.length) return { list: state.screenSubs, source: 'screen' }
    return { list: [], source: '' }
  }

  // ---------- 側邊欄的請求 ----------
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === 'PING') {
      const v = video()
      sendResponse({
        ok: true,
        videoId: currentVideoId(),
        title: document.title.replace(/ - YouTube$/, ''),
        ad: isAd(),
        t: v ? v.currentTime : 0,
        paused: v ? v.paused : true,
        subtitleCount: currentSubs().list.length,
        subtitleSource: currentSubs().source,
      })
      return
    }
    if (msg.type === 'CAPTURE') {
      capture().then(sendResponse).catch((e) => sendResponse({ error: String(e) }))
      return true
    }
    if (msg.type === 'SEEK') {
      const v = video()
      if (v && !isAd()) v.currentTime = msg.t
      sendResponse({ ok: true })
      return
    }
    if (msg.type === 'DIAG') {
      pullCachedSubs().then(diagnose).then(sendResponse)
      return true
    }
    if (msg.type === 'ENABLE_CAPTIONS') {
      askMain('ENABLE_CAPTIONS').then((r) => sendResponse(r || { ok: false }))
      return true
    }
  })
})()
