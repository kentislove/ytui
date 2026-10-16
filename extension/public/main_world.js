// 在 YouTube 頁面本身的環境執行（MAIN world），才讀得到播放器資料與播放器自己下載的字幕。
// 只讀取資料、不修改請求內容；所有資料都透過 postMessage 交給 content.js。
//
// v1.2：
//   1. 攔到的字幕先依影片編號存起來（快取），content.js 隨時可以來拿。
//      v1.1 只在攔到當下送出一次，若 content.js 還沒就緒（影片一開就自動開 CC 時）就會漏接。
//   2. XHR 依 responseType 讀取內容（text／json／arraybuffer／blob），v1.1 只讀 responseText，其他格式會失敗且被吞掉。
//   3. 診斷：記錄攔截次數、讀取失敗次數、頁面實際下載字幕的次數。
(() => {
  if (window.__ytaiMain) return
  window.__ytaiMain = true

  const post = (type, payload) => window.postMessage({ source: 'ytai-main', type, payload }, '*')
  const isTimedText = (u) => typeof u === 'string' && u.includes('/api/timedtext')
  const cache = {}                     // 影片編號 → { url, body, at }
  const diag = { fetchHits: 0, xhrHits: 0, readErrors: 0, lastError: '', emptyBodies: 0 }

  const videoIdOf = (url) => {
    try { return new URL(url, location.href).searchParams.get('v') || '' } catch (e) { return '' }
  }
  const store = (url, body) => {
    // 空內容、"null"、太短的回應不存，避免蓋掉已經存好的正常字幕
    if (!body || body === 'null' || body.length < 20) { diag.emptyBodies++; return }
    const v = videoIdOf(url)
    cache[v] = { url, body, at: Date.now() }
    post('TIMEDTEXT', { url, body })
  }
  const fail = (e) => { diag.readErrors++; diag.lastError = String(e).slice(0, 120) }

  // 1. 攔截 fetch
  const origFetch = window.fetch
  window.fetch = async function (input, init) {
    const res = await origFetch.apply(this, arguments)
    try {
      const url = typeof input === 'string' ? input : (input && input.url) || String(input)
      if (isTimedText(url)) {
        diag.fetchHits++
        res.clone().text().then((body) => store(url, body)).catch(fail)
      }
    } catch (e) { fail(e) }
    return res
  }

  // 2. 攔截 XMLHttpRequest（依 responseType 讀取）
  const origOpen = XMLHttpRequest.prototype.open
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__ytaiUrl = String(url)
    return origOpen.apply(this, arguments)
  }
  const origSend = XMLHttpRequest.prototype.send
  XMLHttpRequest.prototype.send = function () {
    if (isTimedText(this.__ytaiUrl)) {
      diag.xhrHits++
      this.addEventListener('load', () => {
        try {
          const rt = this.responseType
          if (rt === '' || rt === 'text') store(this.__ytaiUrl, this.responseText)
          else if (rt === 'json') store(this.__ytaiUrl, JSON.stringify(this.response))
          else if (rt === 'arraybuffer') store(this.__ytaiUrl, new TextDecoder().decode(this.response))
          else if (rt === 'blob') this.response.text().then((b) => store(this.__ytaiUrl, b)).catch(fail)
          else fail('不支援的 responseType：' + rt)
        } catch (e) { fail(e) }
      })
    }
    return origSend.apply(this, arguments)
  }

  // 3. 影片資料：標題、頻道、說明欄、可用字幕語言
  const player = () => document.querySelector('#movie_player')
  const playerResponse = () => {
    const pl = player()
    return (pl && pl.getPlayerResponse && pl.getPlayerResponse()) || window.ytInitialPlayerResponse || {}
  }
  const captionTracks = () => {
    const p = playerResponse()
    return (p.captions && p.captions.playerCaptionsTracklistRenderer &&
      p.captions.playerCaptionsTracklistRenderer.captionTracks) || []
  }
  const meta = () => {
    const d = playerResponse().videoDetails || {}
    return {
      videoId: d.videoId || '',
      title: d.title || '',
      author: d.author || '',
      description: d.shortDescription || '',
      lengthSeconds: Number(d.lengthSeconds || 0),
      captionLangs: captionTracks().map((t) => t.languageCode + (t.kind ? '-' + t.kind : '')),
    }
  }

  // 4. 自動開啟字幕：依序選繁中、中文、簡中、英文；優先選人工字幕
  const enableCaptions = () => {
    const pl = player()
    const tracks = captionTracks()
    if (!pl || !tracks.length) return false
    const pref = ['zh-Hant', 'zh-TW', 'zh', 'zh-Hans', 'zh-CN', 'en']
    const pick = pref.map((l) => tracks.find((t) => t.languageCode === l && t.kind !== 'asr')).find(Boolean) ||
      pref.map((l) => tracks.find((t) => t.languageCode === l)).find(Boolean) || tracks[0]
    try {
      pl.loadModule('captions')
      pl.setOption('captions', 'track', { languageCode: pick.languageCode })
      return true
    } catch (e) {
      return false
    }
  }

  // 5. 診斷資訊
  const diagnose = () => {
    const pl = player()
    let track = ''
    try { const t = pl && pl.getOption && pl.getOption('captions', 'track'); track = (t && t.languageCode) || '' } catch (e) {}
    const perf = performance.getEntriesByType('resource').filter((e) => e.name.includes('/api/timedtext'))
    return Object.assign({}, diag, {
      hooked: window.fetch !== origFetch,
      pageTimedtextRequests: perf.length,
      pageInitiators: [...new Set(perf.map((e) => e.initiatorType))].join(','),
      cachedVideos: Object.keys(cache).length,
      currentTrack: track,
      captionLangs: captionTracks().map((t) => t.languageCode + (t.kind ? '-' + t.kind : '')).join(','),
    })
  }

  window.addEventListener('message', (e) => {
    if (e.source !== window || !e.data || e.data.source !== 'ytai-content') return
    const { type, id, videoId } = e.data
    if (type === 'GET_META') post('META', Object.assign({ id }, meta()))
    if (type === 'ENABLE_CAPTIONS') post('CAPTIONS_ENABLED', { id, ok: enableCaptions() })
    if (type === 'GET_TIMEDTEXT') post('TIMEDTEXT_CACHE', Object.assign({ id }, cache[videoId] || {}))
    if (type === 'GET_DIAG') post('DIAG', Object.assign({ id }, diagnose()))
  })
})()
