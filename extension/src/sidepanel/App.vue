<script setup lang="ts">
// v3.2：和網頁版同一個後端、同一個 Google 帳號；問答紀錄存在後端（兩邊同步）。
// 截圖、字幕、說明欄的讀取方式沿用 v1.x～v2.2（content.js、main_world.js）。
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { translate, type Lang } from './i18n'
import {
  activeYoutubeTab, ask, backendUrl, BACKENDS, clearHistory, fmt, hasToken, health, history as fetchHistory,
  loadConnection, login, logout, me as fetchMe, older, sendToTab, setBackend, splitTimestamps, VERSION,
  type BackendKey, type Capture, type Health, type HistoryItem, type Ping, type User,
} from './api'

const lang = ref<Lang>('zh-TW')
const t = (key: string, params: Record<string, string | number> = {}) => translate(lang.value, key, params)

const backendKey = ref<BackendKey>('nas')
const server = ref<Health | null>(null)
const user = ref<User | null>(null)
const loginBusy = ref(false)
const loginError = ref('')
const avatarBroken = ref(false)
const ping = ref<Ping | null>(null)
const tabId = ref<number | null>(null)
const question = ref('')
const busy = ref(false)
const errorMsg = ref('')
const answer = ref('')
const answerMeta = ref('')
const answerWarning = ref('')
const lastFrames = ref<{ t: number; data_url: string }[]>([])
const items = ref<HistoryItem[]>([])
const autoCaptions = ref(true)
const webSearch = ref(false)
const speaking = ref(false)
const listening = ref(false)
const micDenied = ref(false)
const theme = ref<'light' | 'dark' | ''>('')
let recognition: any = null
let timer: number | undefined

const answerParts = computed(() => splitTimestamps(answer.value))
const needUpdate = computed(() => !!server.value?.min_extension && older(VERSION, server.value.min_extension))

const statusLine = computed(() => {
  if (!server.value) return { cls: 'bad', text: t('status.backend_down', { u: backendUrl() }) }
  if (needUpdate.value) return { cls: 'bad', text: t('status.update', { v: VERSION, m: server.value.min_extension! }) }
  if (!server.value.ok) return { cls: 'bad', text: server.value.gpu_message || 'error' }
  return { cls: 'ok', text: t('status.cloud_ok') }
})

const videoLine = computed(() => {
  if (!ping.value) return { cls: 'warn', text: t('status.not_youtube') }
  if (ping.value.ad) return { cls: 'warn', text: t('status.ad') }
  const src = ping.value.subtitleSource === 'track' ? t('status.src_track') : t('status.src_screen')
  const sub = ping.value.subtitleCount
    ? t('status.subtitles', { n: ping.value.subtitleCount, src }) : t('status.no_subtitles')
  return { cls: 'ok', text: sub }
})

const quotaLine = computed(() => {
  const q = user.value?.quota
  if (!q) return { cls: '', text: '' }
  if (q.reason === 'admin') return { cls: '', text: t('quota.admin', { u: q.used }) }
  if (q.reason === 'full') return { cls: 'bad', text: t('quota.full') }
  return { cls: q.remaining ? '' : 'bad', text: t('quota.free', { r: q.remaining ?? 0, l: q.limit ?? 0 }) }
})

const canAsk = computed(() => !busy.value && !!question.value.trim() && !!ping.value && !ping.value.ad
  && !!server.value && !needUpdate.value && !!user.value)

async function refresh() {
  server.value = await health()
  const tab = await activeYoutubeTab()
  tabId.value = tab ? tab.id : null
  ping.value = tab ? await sendToTab<Ping>(tab.id, { type: 'PING' }) : null
  if (user.value && !hasToken()) user.value = null   // 後端說登入過期了
}

async function loadUser() {
  user.value = await fetchMe()
  avatarBroken.value = false
  items.value = user.value ? await fetchHistory() : []
}

async function doLogin() {
  loginBusy.value = true; loginError.value = ''
  const r = await login()
  loginBusy.value = false
  if (r.user) { user.value = r.user; avatarBroken.value = false; items.value = await fetchHistory() }
  else loginError.value = t('login.failed', { e: r.error === 'network' ? t('error.network') : (r.error || '') })
}
async function doLogout() {
  await logout()
  user.value = null; items.value = []; answer.value = ''
}
async function changeBackend(k: BackendKey) {
  await setBackend(k)
  backendKey.value = k
  user.value = null; items.value = []; answer.value = ''
  await refresh()
}

async function submit() {
  if (!canAsk.value || tabId.value === null) return
  busy.value = true
  errorMsg.value = ''
  stopSpeaking()
  try {
    const cap = await sendToTab<Capture>(tabId.value, { type: 'CAPTURE' })
    if (!cap || cap.error) {
      errorMsg.value = cap?.error === 'AD' ? t('status.ad') : t('error.capture')
      return
    }
    lastFrames.value = cap.frames
    const q = question.value.trim()
    const r = await ask(cap, q, lang.value, webSearch.value)
    if (r.quota && user.value) user.value = { ...user.value, quota: r.quota }
    if (!r.answer) {
      if (r.status === 401) { user.value = null; errorMsg.value = t('error.login') }
      else errorMsg.value = r.error === 'network' ? t('error.network') : (r.message || r.error || 'error')
      return
    }
    answer.value = r.answer
    answerWarning.value = r.warning || ''
    answerMeta.value = t('answer.meta', {
      s: r.secs ?? 0, f: r.vision_used === false ? 0 : (r.frames_used ?? 0),
      sub: r.had_subtitles ? t('answer.with_sub') : t('answer.without_sub'),
    }) + (r.model ? t('answer.model', { m: r.model.split(':').slice(1).join(':'), n: r.tries ?? 1 }) : '')
      + (r.searched ? t('answer.searched') : '')
    question.value = ''
    items.value = await fetchHistory()
  } finally {
    busy.value = false
    refresh()
  }
}

function seek(sec: number) {
  if (tabId.value !== null) sendToTab(tabId.value, { type: 'SEEK', t: sec })
}

// ---------- 朗讀（瀏覽器內建，不花錢） ----------
function speak() {
  const text = answer.value.replace(/【[^】]*】/g, '')
  const u = new SpeechSynthesisUtterance(text)
  u.lang = lang.value === 'en' ? 'en-US' : 'zh-TW'
  u.onend = () => { speaking.value = false }
  speechSynthesis.cancel()
  speechSynthesis.speak(u)
  speaking.value = true
}
function stopSpeaking() { speechSynthesis.cancel(); speaking.value = false }

// ---------- 按一下說話（瀏覽器內建語音辨識） ----------
function toggleMic() {
  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SR) { micDenied.value = true; return }
  if (listening.value) { recognition?.stop(); return }
  recognition = new SR()
  recognition.lang = lang.value === 'en' ? 'en-US' : 'zh-TW'
  recognition.interimResults = false
  recognition.onresult = (e: any) => { question.value += e.results[0][0].transcript }
  recognition.onerror = (e: any) => { if (e.error === 'not-allowed') micDenied.value = true }
  recognition.onend = () => { listening.value = false }
  micDenied.value = false
  listening.value = true
  recognition.start()
}
function grantMic() { chrome.tabs.create({ url: chrome.runtime.getURL('mic.html') }) }

// ---------- 診斷資訊（v1.2：確認字幕檔有沒有攔截到） ----------
const diagText = ref('')
async function runDiag() {
  if (tabId.value === null) { diagText.value = t('status.not_youtube'); return }
  const d = await sendToTab<Record<string, unknown>>(tabId.value, { type: 'DIAG' })
  diagText.value = d ? JSON.stringify(d, null, 1) : t('error.capture')
}

// ---------- 日／月 ----------
const isDark = () => theme.value === 'dark' || (!theme.value && matchMedia('(prefers-color-scheme: dark)').matches)
function applyTheme() {
  if (theme.value) document.documentElement.dataset.theme = theme.value
  else delete document.documentElement.dataset.theme
}
function toggleTheme() {
  theme.value = isDark() ? 'light' : 'dark'
  applyTheme()
  chrome.storage.local.set({ theme: theme.value })
}

// ---------- 設定與紀錄 ----------
async function loadSettings() {
  const s = await chrome.storage.local.get({ lang: 'zh-TW', autoCaptions: true, webSearch: false, theme: '' })
  lang.value = s.lang
  autoCaptions.value = s.autoCaptions
  webSearch.value = s.webSearch
  theme.value = s.theme
  applyTheme()
  backendKey.value = await loadConnection()
}
function setLang(l: Lang) { lang.value = l; chrome.storage.local.set({ lang: l }) }
function saveWebSearch() { chrome.storage.local.set({ webSearch: webSearch.value }) }
function setAutoCaptions() {
  chrome.storage.local.set({ autoCaptions: autoCaptions.value })
  if (autoCaptions.value && tabId.value !== null) sendToTab(tabId.value, { type: 'ENABLE_CAPTIONS' })
}
async function clearAll() {
  if (!confirm(t('history.clear_confirm'))) return
  await clearHistory()
  items.value = []
}
function exportNotes() {
  const lines = [`# ${t('history.title')}`, '']
  for (const h of items.value) {
    lines.push(`## ${h.title || h.video_id}（${fmt(h.pause)}）`)
    if (h.video_id && h.video_id !== 'test') lines.push(`https://www.youtube.com/watch?v=${h.video_id}&t=${Math.floor(h.pause)}s`)
    lines.push('', `**Q：** ${h.question}`, '', h.answer, '', `_${h.time}_`, '')
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `youtube-ai-notes-${new Date().toISOString().slice(0, 10)}.md`
  a.click()
  URL.revokeObjectURL(a.href)
}
function openHistory(h: HistoryItem) {
  answer.value = h.answer
  answerWarning.value = ''
  answerMeta.value = h.time.replace('T', ' ').slice(0, 16)
  lastFrames.value = []
  if (tabId.value !== null && ping.value?.videoId === h.video_id) seek(h.pause)
  else if (h.video_id && h.video_id !== 'test')
    chrome.tabs.create({ url: `https://www.youtube.com/watch?v=${h.video_id}&t=${Math.floor(h.pause)}s` })
}

onMounted(async () => {
  await loadSettings()
  await refresh()
  await loadUser()
  timer = window.setInterval(refresh, 2000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <main>
    <header>
      <h1><span class="mark" aria-hidden="true"></span>{{ t('app.title') }}</h1>
      <div class="tools">
        <button class="round" :title="t(isDark() ? 'theme.to_light' : 'theme.to_dark')"
          :aria-label="t(isDark() ? 'theme.to_light' : 'theme.to_dark')" @click="toggleTheme">
          <svg v-if="isDark()" viewBox="0 0 24 24" aria-hidden="true" class="line"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.4M12 19.1v2.4M2.5 12h2.4M19.1 12h2.4M5.3 5.3l1.7 1.7M17 17l1.7 1.7M5.3 18.7 7 17M17 7l1.7-1.7"/></svg>
          <svg v-else viewBox="0 0 24 24" aria-hidden="true" class="solid"><path d="M20 14.5A8.2 8.2 0 0 1 9.5 4a8.2 8.2 0 1 0 10.5 10.5Z"/></svg>
        </button>
        <div class="lang">
          <button :class="{ on: lang === 'zh-TW' }" @click="setLang('zh-TW')">{{ t('lang.tw') }}</button>
          <button :class="{ on: lang === 'en' }" @click="setLang('en')">{{ t('lang.en') }}</button>
        </div>
      </div>
    </header>

    <section class="status">
      <p :class="statusLine.cls">{{ statusLine.text }}</p>
    </section>

    <!-- 沒登入 -->
    <section v-if="!user" class="sheet">
      <h2>{{ t('login.title') }}</h2>
      <p class="fine">{{ t('login.note') }}</p>
      <button class="primary wide" :disabled="loginBusy || !server" @click="doLogin">
        {{ loginBusy ? t('login.busy') : t('login.button') }}</button>
      <p v-if="loginError" class="bad small">{{ loginError }}</p>
    </section>

    <template v-else>
      <section class="account">
        <img v-if="user.picture && !avatarBroken" :src="user.picture" alt="" referrerpolicy="no-referrer" @error="avatarBroken = true">
        <span v-else class="initial" aria-hidden="true">{{ (user.name || user.email).charAt(0).toUpperCase() }}</span>
        <div class="who"><b>{{ user.name || user.email }}</b><span :class="['fine', quotaLine.cls]">{{ quotaLine.text }}</span></div>
        <button class="quiet small" @click="doLogout">{{ t('login.logout') }}</button>
      </section>

      <section class="sheet">
        <div class="moment">
          <span class="moment-time">{{ ping ? fmt(ping.t) : '–:––' }}</span>
          <div class="moment-note">
            <b v-if="ping">{{ ping.title }}</b>
            <span :class="videoLine.cls">{{ videoLine.text }}</span>
          </div>
        </div>
        <textarea v-model="question" :placeholder="t('ask.placeholder')" rows="3"
          @keydown.enter.exact.prevent="submit" />
        <div class="row">
          <button class="quiet" :class="{ on: listening }" @click="toggleMic">
            {{ listening ? t('ask.mic_stop') : t('ask.mic') }}
          </button>
          <button class="primary grow" :disabled="!canAsk" @click="submit">
            {{ busy ? t('ask.sending') : t('ask.send') }}
          </button>
        </div>
        <p v-if="micDenied" class="warn small">{{ t('ask.mic_denied') }}
          <button class="link" @click="grantMic">{{ t('ask.mic_grant') }}</button></p>
        <label class="check"><input type="checkbox" v-model="webSearch" @change="saveWebSearch" />
          {{ t('ask.web_search') }} <small class="fine">{{ t('ask.web_search_note') }}</small></label>
        <label class="check"><input type="checkbox" v-model="autoCaptions" @change="setAutoCaptions" />
          {{ t('ask.auto_captions') }}</label>
        <p v-if="errorMsg" class="bad small">{{ errorMsg }}</p>

        <div v-if="answer" class="answer">
          <div class="row between">
            <h2>{{ t('answer.title') }}</h2>
            <button class="quiet small" @click="speaking ? stopSpeaking() : speak()">
              {{ speaking ? t('answer.stop') : t('answer.read') }}</button>
          </div>
          <p class="text">
            <template v-for="(p, i) in answerParts" :key="i">
              <button v-if="'t' in p" class="ts" @click="seek(p.t)">{{ p.label }}</button>
              <span v-else>{{ p.text }}</span>
            </template>
          </p>
          <p class="fine">{{ answerMeta }}</p>
          <p v-if="answerWarning" class="warn small">{{ answerWarning }}</p>
          <details v-if="lastFrames.length">
            <summary>{{ t('answer.frames') }}</summary>
            <div class="frames">
              <figure v-for="f in lastFrames" :key="f.t" @click="seek(f.t)">
                <img :src="f.data_url" alt="" /><figcaption>{{ fmt(f.t) }}</figcaption>
              </figure>
            </div>
          </details>
          <p class="fine">{{ t('answer.disclaimer') }}</p>
        </div>
      </section>

      <section class="log">
        <div class="row between head">
          <h2>{{ t('history.title') }} <small class="fine">{{ t('history.synced') }}</small></h2>
          <div class="row">
            <button class="quiet small" :disabled="!items.length" @click="exportNotes">{{ t('history.export') }}</button>
            <button class="quiet small danger" :disabled="!items.length" @click="clearAll">{{ t('history.clear') }}</button>
          </div>
        </div>
        <p v-if="!items.length" class="fine">{{ t('history.empty') }}</p>
        <ul>
          <li v-for="h in items" :key="h.id" tabindex="0" @click="openHistory(h)" @keydown.enter="openHistory(h)">
            <span class="h-time">{{ fmt(h.pause) }}</span>
            <span><span class="q">{{ h.question }}</span><span class="fine">{{ h.title || h.video_id }}</span></span>
          </li>
        </ul>
      </section>
    </template>

    <details class="more">
      <summary>{{ t('settings.title') }}</summary>
      <p class="label">{{ t('settings.backend') }}</p>
      <label class="check"><input type="radio" name="backend" :checked="backendKey === 'nas'" @change="changeBackend('nas')" />
        {{ t('settings.nas') }}</label>
      <label class="check"><input type="radio" name="backend" :checked="backendKey === 'local'" @change="changeBackend('local')" />
        {{ t('settings.local') }}</label>
      <p class="fine">{{ t('settings.note') }}</p>
      <p class="fine">{{ t('settings.version', { v: VERSION }) }}｜{{ BACKENDS[backendKey] }}</p>
    </details>

    <details class="more" @toggle="runDiag">
      <summary>{{ t('diag.title') }}</summary>
      <button class="quiet small" @click="runDiag">{{ t('diag.refresh') }}</button>
      <pre>{{ diagText }}</pre>
    </details>
  </main>
</template>

<style>
/* 與網頁版 v3.1.2 同一套色票：墨藍、不鏽鋼灰、白紙、薑黃（唯一強調色） */
:root {
  --ink: #1c2733; --muted: #5d6b77; --line: #d3d9de; --paper: #eef1f3; --sheet: #ffffff;
  --turmeric: #e6a019; --turmeric-ink: #1c2733; --turmeric-soft: #fbf0d6; --basil: #3f7d52; --chili: #b8432f;
  --display: "Bricolage Grotesque", "Segoe UI", system-ui, sans-serif;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --ink: #e6ebee; --muted: #8e9ca7; --line: #2a3540; --paper: #10171e; --sheet: #182129;
    --turmeric: #f2b23c; --turmeric-ink: #10171e; --turmeric-soft: #2c2512; --basil: #6fb685; --chili: #e57a63; color-scheme: dark; }
}
:root[data-theme="dark"] { --ink: #e6ebee; --muted: #8e9ca7; --line: #2a3540; --paper: #10171e; --sheet: #182129;
  --turmeric: #f2b23c; --turmeric-ink: #10171e; --turmeric-soft: #2c2512; --basil: #6fb685; --chili: #e57a63; color-scheme: dark; }

* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink);
  font: 14px/1.65 "Noto Sans TC", "Microsoft JhengHei", system-ui, sans-serif; }
main { padding: 12px 14px 28px; }
header { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
h1 { font: 800 15px/1.2 var(--display); margin: 0; display: flex; align-items: center; gap: 8px; }
h2 { font-size: 14px; margin: 0; }
.mark { width: 18px; height: 18px; border-radius: 5px; background: var(--ink); position: relative; flex: none; }
.mark::before, .mark::after { content: ""; position: absolute; top: 5px; width: 2.5px; height: 8px; border-radius: 2px; background: var(--turmeric); }
.mark::before { left: 5.5px; } .mark::after { right: 5.5px; }
.tools { display: flex; align-items: center; gap: 6px; }
section { margin-top: 12px; }
button { font: inherit; border: 1px solid var(--line); background: transparent; color: var(--ink);
  border-radius: 8px; padding: 6px 12px; cursor: pointer; }
button:disabled { opacity: .45; cursor: not-allowed; }
button.primary { background: var(--turmeric); border-color: var(--turmeric); color: var(--turmeric-ink); font-weight: 700; }
button.quiet.on { border-color: var(--turmeric); background: var(--turmeric-soft); }
button.small { padding: 4px 10px; font-size: 13px; }
button.danger { color: var(--chili); }
button.wide { width: 100%; margin-top: 10px; padding: 9px; }
button.round { width: 30px; height: 30px; padding: 0; border-radius: 50%; display: grid; place-items: center; }
.round svg { width: 16px; height: 16px; }
.round .line { fill: none; stroke: var(--ink); stroke-width: 1.8; stroke-linecap: round; }
.round .solid { fill: var(--ink); }
:focus-visible { outline: 2px solid var(--turmeric); outline-offset: 2px; }
.lang { display: flex; border: 1px solid var(--line); border-radius: 999px; padding: 2px; }
.lang button { border: 0; border-radius: 999px; padding: 2px 9px; font-size: 12px; color: var(--muted); }
.lang button.on { background: var(--ink); color: var(--sheet); }

.status p { margin: 0; font-size: 12.5px; }
.status p::before { content: ""; display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 6px; vertical-align: 1px; }
.status .ok { color: var(--muted); } .status .ok::before { background: var(--basil); }
.status .bad::before { background: var(--chili); }
.ok { color: var(--basil); } .warn { color: var(--turmeric); } .bad { color: var(--chili); }
.fine { color: var(--muted); font-size: 12px; display: block; }
.small { font-size: 13px; margin: 6px 0 0; }

.sheet { background: var(--sheet); border: 1px solid var(--line); border-radius: 12px; padding: 14px; }
.account { display: flex; align-items: center; gap: 10px; }
.account img, .initial { width: 30px; height: 30px; border-radius: 50%; flex: none; }
.initial { display: grid; place-items: center; background: var(--turmeric); color: var(--turmeric-ink); font-weight: 700; }
.who { flex: 1; min-width: 0; line-height: 1.35; }
.who b { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.moment { display: grid; grid-template-columns: auto 1fr; gap: 12px; align-items: center; margin-bottom: 10px; }
.moment-time { font: 800 38px/0.9 var(--display); letter-spacing: -.03em; font-variant-numeric: tabular-nums; }
.moment-note { font-size: 12px; line-height: 1.45; min-width: 0; }
.moment-note b { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; font-size: 12.5px; }
textarea { width: 100%; font: inherit; color: var(--ink); background: var(--sheet);
  border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; resize: vertical; }
textarea:focus { outline: none; border-color: var(--turmeric); box-shadow: 0 0 0 3px var(--turmeric-soft); }
.row { display: flex; gap: 8px; align-items: center; margin-top: 8px; }
.row.between, .between { justify-content: space-between; }
.grow { flex: 1; }
.check { display: flex; align-items: center; gap: 6px; font-size: 13px; margin-top: 8px; flex-wrap: wrap; }
.check input { margin: 0; accent-color: var(--turmeric); }
.check .fine { display: inline; }
.link { border: none; background: none; color: var(--ink); text-decoration: underline; text-decoration-color: var(--turmeric); padding: 0 4px; }

.answer { margin-top: 12px; padding-top: 12px; border-top: 1px dashed var(--line); }
.text { white-space: pre-wrap; margin: 8px 0; font-size: 14.5px; line-height: 1.75; }
.ts { font: 700 13px/1 var(--display); font-variant-numeric: tabular-nums; padding: 2px 6px; margin: 0 1px; border-radius: 999px;
  border-color: var(--turmeric); background: var(--turmeric-soft); color: var(--ink); }
.frames { display: grid; grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)); gap: 6px; margin-top: 6px; }
figure { margin: 0; cursor: pointer; }
figure img { width: 100%; border-radius: 4px; display: block; }
figcaption { font-size: 11px; text-align: center; color: var(--muted); }

.log .head { padding-bottom: 6px; border-bottom: 2px solid var(--ink); margin-top: 0; }
.log h2 small { display: inline; font-weight: 400; margin-left: 4px; }
.log ul { list-style: none; padding: 0; margin: 0; }
.log li { display: grid; grid-template-columns: 46px 1fr; gap: 10px; align-items: baseline; padding: 8px 2px;
  border-bottom: 1px solid var(--line); cursor: pointer; }
.log li:hover .q { text-decoration: underline; text-decoration-color: var(--turmeric); text-underline-offset: 3px; }
.h-time { font: 800 15px/1 var(--display); font-variant-numeric: tabular-nums; text-align: right; }
.q { display: block; font-weight: 700; }

details summary { cursor: pointer; font-size: 12.5px; color: var(--muted); }
.more { margin-top: 14px; }
.more .label { margin: 8px 0 0; font-size: 13px; font-weight: 700; }
.more pre { white-space: pre-wrap; word-break: break-all; background: var(--sheet); border: 1px solid var(--line);
  border-radius: 6px; padding: 6px; margin: 6px 0 0; font-size: 11px; }
</style>
