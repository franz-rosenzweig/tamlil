(() => {
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const isHe = s => /[א-ת]/.test(s || '');
const dirOf = s => isHe(s) ? 'rtl' : 'ltr';
const fmt = ms => { let s = Math.max(0, Math.round(ms / 1000)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
  return (h ? h + ':' + String(m).padStart(2, '0') : String(m)) + ':' + String(x).padStart(2, '0'); };
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const day = d => d && d.length === 8 ? `${+d.slice(6)} ${MON[+d.slice(4, 6) - 1]} ${d.slice(0, 4)}` : '';
const hours = sec => sec >= 3600 ? (sec / 3600).toFixed(sec >= 36000 ? 0 : 1) + ' h' : Math.round(sec / 60) + ' min';
const LANG = {he: 'עברית', en: 'English'};
const ORIGIN = {uploader: 'Captions', youtube_auto: 'Auto captions', whisper: 'Whisper'};
const WHY = {exact: 'Exact', form: 'Form', spelling: 'Spelling'};
let CFG = {player: ''}, ME = {};

async function api(path, opts = {}) {
  const r = await fetch(path, {headers: {'content-type': 'application/json'}, ...opts});
  if (r.status === 401) { location.href = '/login'; throw new Error('sign in'); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}
let toastT;
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => t.hidden = true, 3500); }
async function copy(text) {
  try { await navigator.clipboard.writeText(text); toast('Copied'); }
  catch { prompt('Copy', text); }
}
const svg = d => `<svg class="ico" viewBox="0 0 16 16" width="13" height="13" fill="currentColor" aria-hidden="true">${d}</svg>`;
const PAUSE = svg('<rect x="3" y="2.5" width="3.6" height="11" rx="1"/><rect x="9.4" y="2.5" width="3.6" height="11" rx="1"/>');
const PLAY = svg('<path d="M4.5 2.6v10.8c0 .6.6 1 1.1.7l8.4-5.4c.5-.3.5-1 0-1.3L5.6 1.9c-.5-.3-1.1.1-1.1.7z"/>');
const EXPORTS = [['txt', 'Text · .txt'], ['srt', 'Subtitles · .srt'], ['vtt', 'Subtitles · .vtt'], ['json', 'JSON']];
document.addEventListener('click', e => { for (const d of $$('details.menu[open]')) if (!d.contains(e.target)) d.open = false; });

function marked(text, ranges) {
  if (!ranges || !ranges.length) return esc(text);
  const rs = ranges.slice().sort((a, b) => a[0] - b[0] || b[1] - a[1]);
  let out = '', pos = 0;
  for (const [s, e, k] of rs) { if (s < pos) continue; out += esc(text.slice(pos, s)) + `<mark class="k-${k}">${esc(text.slice(s, e))}</mark>`; pos = e; }
  return out + esc(text.slice(pos));
}
const whyHTML = why => (why || []).map(([k, d]) => `<span class="b b-${k}">${WHY[k] || k}${d ? ` · <bdi>${esc(d)}</bdi>` : ''}</span>`).join('');
const thumb = id => `${CFG.player}/vi/${id}/mqdefault.jpg`;
const ytLink = (id, ms) => `https://www.youtube.com/watch?v=${id}&t=${Math.floor(ms / 1000)}s`;
const embed = (id, ms) => `${CFG.player}/embed/${id}?t=${Math.floor(ms / 1000)}&autoplay=1`;

function parseHash() {
  const [path, qs] = (location.hash.slice(1) || '/search').split('?');
  return {parts: path.split('/').filter(Boolean), params: new URLSearchParams(qs || '')};
}
function go(path) { location.hash = path; }

/* ---------- search ---------- */
const S = {q: '', lang: 'all', src: '', title: '', from: '', to: '', sort: 'best', sources: null};
const SORTS = [['best', 'Best match'], ['newest', 'Newest'], ['oldest', 'Oldest'], ['moments', 'Most moments']];
function searchHash(over = {}) {
  const v = {q: S.q, lang: S.lang, src: S.src, title: S.title, from: S.from, to: S.to, sort: S.sort, ...over};
  const p = new URLSearchParams();
  for (const [k, x] of Object.entries(v)) if (x && !(k === 'lang' && x === 'all') && !(k === 'sort' && x === 'best')) p.set(k, x);
  return '/search?' + p.toString();
}
async function viewSearch(params) {
  for (const k of ['q', 'title', 'from', 'to', 'src']) S[k] = params.get(k) || '';
  S.lang = params.get('lang') || 'all'; S.sort = params.get('sort') || 'best';
  S.sources = (await api('/api/sources')).sources;
  const filtered = S.src || S.title || S.from || S.to;
  $('#main').innerHTML = `
    <form class="sbar" id="sform" role="search">
      <input type="search" id="q" dir="auto" autocomplete="off" value="${esc(S.q)}" placeholder="Search" aria-label="Search">
      <div class="seg" role="group" aria-label="Language">${[['all', 'All'], ['he', 'עברית'], ['en', 'English']].map(([k, l]) =>
        `<button type="button" data-lang="${k}" aria-pressed="${S.lang === k}">${l}</button>`).join('')}</div>
    </form>
    <div class="filters">
      <select id="s-src" aria-label="Channel" class="${S.src ? 'on' : ''}"><option value="">All channels</option>${S.sources.map(x =>
        `<option value="${x.id}" ${String(x.id) === S.src ? 'selected' : ''}>${esc(x.title || x.url)}</option>`).join('')}</select>
      <input type="search" id="s-title" dir="auto" autocomplete="off" value="${esc(S.title)}" placeholder="Title" aria-label="Words in the title" class="${S.title ? 'on' : ''}">
      <label class="fdate">From<input type="date" id="s-from" value="${esc(S.from)}" class="${S.from ? 'on' : ''}"></label>
      <label class="fdate">To<input type="date" id="s-to" value="${esc(S.to)}" class="${S.to ? 'on' : ''}"></label>
      <select id="s-sort" aria-label="Sort">${SORTS.map(([k, l]) => `<option value="${k}" ${S.sort === k ? 'selected' : ''}>${l}</option>`).join('')}</select>
      <button type="button" class="linkish clear" id="s-clear" ${filtered ? '' : 'hidden'}>Clear</button>
    </div>
    <div class="meta-line" id="qmeta"></div>
    <div class="results" id="results"></div>`;
  const input = $('#q');
  if (!S.q) input.focus();
  $('#sform').addEventListener('submit', e => { e.preventDefault(); go(searchHash({q: input.value.trim()})); });
  $$('[data-lang]').forEach(b => b.addEventListener('click', () => go(searchHash({q: input.value.trim(), lang: b.dataset.lang}))));
  const set = (k, el) => el.addEventListener('change', () => go(searchHash({q: input.value.trim(), [k]: el.value.trim()})));
  set('src', $('#s-src')); set('title', $('#s-title')); set('from', $('#s-from')); set('to', $('#s-to')); set('sort', $('#s-sort'));
  $('#s-clear').addEventListener('click', () => go(searchHash({q: input.value.trim(), src: '', title: '', from: '', to: ''})));
  if (!S.q) { await emptyState(); return; }
  $('#results').innerHTML = '<div class="empty">…</div>';
  const qs = new URLSearchParams({q: S.q, lang: S.lang, sort: S.sort});
  if (S.src) qs.set('source', S.src);
  if (S.title) qs.set('title', S.title);
  if (S.from) qs.set('date_from', S.from);
  if (S.to) qs.set('date_to', S.to);
  const res = await api(`/api/search?${qs}`);
  const words = res.query.words.map(w => `<span class="forms" dir="auto">${w.forms.map(esc).join(' · ')}</span>`).join(' &nbsp;+&nbsp; ');
  $('#qmeta').innerHTML = `${words}<span class="count">${res.results.length ? `${res.moments} moments · ${res.results.length} videos` : ''}</span>`;
  $('#results').innerHTML = res.results.length ? res.results.map(card).join('') : '<div class="empty">0</div>';
}
async function emptyState() {
  const {sources} = await api('/api/sources');
  const vids = sources.reduce((a, s) => a + (s.ready || 0), 0), secs = sources.reduce((a, s) => a + (s.seconds || 0), 0);
  $('#results').innerHTML = sources.length
    ? `<div class="empty mono">${vids} videos · ${hours(secs)}</div>`
    : `<div class="empty"><a class="btn primary" href="#/library">Add a channel</a></div>`;
}
function card(r) {
  const v = r.video, more = r.moments - r.top.length, t0 = r.top[0].start_ms;
  const marks = v.duration ? r.marks.map(ms => `<i style="left:${Math.min(100, ms / 10 / v.duration).toFixed(2)}%"></i>`).join('') : '';
  const link = (ms) => `#/v/${v.id}?t=${ms}&q=${encodeURIComponent(S.q)}`;
  return `<article class="rcard">
    <a class="thumb" href="${link(t0)}" style="background-image:url('${thumb(v.id)}')" aria-label="${esc(v.title)}">${v.duration ? `<span class="dur">${fmt(v.duration * 1000)}</span>` : ''}</a>
    <div class="rhead">
      <h3 class="rtitle" dir="auto"><a class="linkish" href="${link(t0)}">${esc(v.title)}</a></h3>
      <div class="rmeta"><button class="linkish chan" data-src="${v.source_id}" dir="auto" title="Only this channel">${esc(v.channel)}</button><span>${day(v.upload_date)}</span><span class="src src-${v.origin}">${ORIGIN[v.origin] || ''}</span><span>${LANG[v.lang] || ''}</span></div>
      ${marks ? `<div class="strip" dir="ltr">${marks}</div>` : ''}
    </div>
    <div class="rmoments"><ol class="moments">${r.top.map(m => `
      <li class="moment" dir="${dirOf(m.text)}"><a class="ts" dir="ltr" href="${link(m.start_ms)}">${fmt(m.start_ms)}</a>
        <div><p class="line">${marked(m.text, m.ranges)}</p><div class="why" dir="ltr">${whyHTML(m.why)}</div></div></li>`).join('')}
    </ol>${more > 0 ? `<a class="more" href="${link(t0)}">+${more}</a>` : ''}</div>
  </article>`;
}

/* ---------- video ---------- */
async function viewVideo(id, params) {
  const q = params.get('q') || '', t = +(params.get('t') || 0);
  const data = await api(`/api/videos/${id}?q=${encodeURIComponent(q)}`);
  const v = data.video, segs = data.segments, hits = new Map(data.hits.map(h => [h.idx, h]));
  const hitTimes = segs.filter(s => hits.has(s.idx)).map(s => s.start_ms);
  let now = t;
  $('#main').innerHTML = `
    ${q ? `<button class="back" id="back">← <bdi>${esc(q)}</bdi></button>` : ''}
    <div class="vgrid">
      <div>
        <div class="player"><iframe id="frame" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen src="${embed(id, t)}"></iframe></div>
        ${v.duration && hitTimes.length ? `<div class="scrub" dir="ltr"><div class="rail"></div>${hitTimes.map(ms =>
          `<button class="tk" data-seek="${ms}" style="left:${Math.min(100, ms / 10 / v.duration).toFixed(2)}%" title="${fmt(ms)}"></button>`).join('')}</div>` : ''}
      </div>
      <div class="vmeta">
        <h2 dir="auto">${esc(v.title)}</h2>
        <dl>
          <dt>Channel</dt><dd dir="auto">${esc(v.channel)}</dd>
          <dt>Date</dt><dd>${day(v.upload_date)}</dd>
          <dt>Length</dt><dd>${v.duration ? fmt(v.duration * 1000) : ''}</dd>
          <dt>Language</dt><dd>${LANG[v.lang] || v.lang || ''}</dd>
          <dt>Text</dt><dd><span class="src src-${v.origin}">${ORIGIN[v.origin] || v.state}</span>${v.origin === 'whisper' && v.model ? ` <span class="muted">· ${esc(v.model.includes('ivrit') ? 'ivrit.ai' : v.model)}</span>` : ''}</dd>
          ${q ? `<dt>Matches</dt><dd>${hitTimes.length}</dd>` : ''}
        </dl>
        <div class="vbtns">
          ${hitTimes.length ? `<button class="btn small" id="prev">←</button><button class="btn small" id="next">→</button>` : ''}
          <a class="btn small" id="yt" href="${ytLink(id, t)}" target="_blank" rel="noopener">YouTube ↗</a>
          ${ME.chat ? '<button class="btn small" id="askv">Ask</button>' : ''}
          <button class="btn small" id="share" aria-expanded="false">Share</button>
          <details class="menu"><summary class="btn small">Export</summary><div class="pop">${EXPORTS.map(([f, l]) =>
            `<a href="/api/videos/${esc(id)}/export?format=${f}" download>${l}</a>`).join('')}</div></details>
        </div>
        <div class="sharebox" id="sharebox" hidden>
          <div class="shareurl"><input type="text" id="share-url" readonly dir="ltr" aria-label="Link"><button class="btn small primary" id="share-copy">Copy</button></div>
          <div class="shareopts">
            <label class="check"><input type="checkbox" id="share-t" checked> <span id="share-at"></span></label>
            ${navigator.share ? '<button class="linkish" id="share-send">Send…</button>' : ''}
            <button class="linkish" id="share-yt">Copy YouTube link</button>
          </div>
        </div>
      </div>
    </div>
    <div class="tbar"><input type="search" id="find" dir="auto" placeholder="Find" aria-label="Find in transcript"><span class="count" id="tcount">${segs.length} lines</span></div>
    <ol class="tlines" id="tlines"></ol>`;
  const back = $('#back'); if (back) back.addEventListener('click', () => go(searchHash({q})));
  const strip = s => s.normalize('NFD').replace(/[֑-ׇ]/g, '').toLowerCase();
  function lines(find) {
    const f = strip(find || '').trim(); let n = 0;
    $('#tlines').innerHTML = segs.map(s => {
      const h = hits.get(s.idx); let ranges = h ? h.ranges.slice() : [];
      if (f) { const low = strip(s.text); let i = low.indexOf(f); if (i >= 0) n++; while (i >= 0) { ranges.push([i, i + f.length, 'find']); i = low.indexOf(f, i + f.length); } }
      return `<li class="tl${h ? ' hit' : ''}" dir="${dirOf(s.text)}" data-ms="${s.start_ms}"><button class="ts" dir="ltr" data-seek="${s.start_ms}">${fmt(s.start_ms)}</button>
        <div><p class="line">${marked(s.text, ranges)}</p>${h ? `<div class="why" dir="ltr">${whyHTML(h.why)}</div>` : ''}</div></li>`;
    }).join('');
    $('#tcount').textContent = f ? `${n} / ${segs.length}` : `${segs.length} lines`;
    mark(false);
  }
  function mark(scroll, behavior = 'smooth') {
    let cur = null;
    const sec = Math.floor(now / 1000);       // a cited 0:50 is the line shown as 0:50, even when it starts at 50.4 s
    for (const li of $$('.tl')) { const on = Math.floor(li.dataset.ms / 1000) <= sec; if (on) cur = li; li.classList.remove('now'); }
    if (cur) { cur.classList.add('now'); if (scroll) cur.scrollIntoView({block: 'center', behavior}); }
    $$('.tk').forEach(k => k.classList.toggle('cur', +k.dataset.seek === now));
  }
  let shareBase = '';
  const shareLink = () => shareBase + ($('#share-t').checked && now ? `?t=${Math.floor(now / 1000)}` : '');
  function shareText() { $('#share-at').textContent = `At ${fmt(now)}`; if (shareBase) $('#share-url').value = shareLink(); }
  $('#share').onclick = async () => {
    const box = $('#sharebox'), opening = box.hidden;
    box.hidden = !opening; $('#share').setAttribute('aria-expanded', String(opening));
    if (!opening) return;
    if (!shareBase) {
      try { shareBase = (await api(`/api/videos/${id}/share`, {method: 'POST'})).url; }
      catch (err) { toast(err.message); return; }
    }
    shareText(); $('#share-url').select();
  };
  $('#share-t').onchange = shareText;
  if ($('#askv')) $('#askv').onclick = async () => {
    try { go('/chat/' + (await api('/api/chats', {method: 'POST', body: JSON.stringify({video_id: id})})).id); }
    catch (err) { toast(chatSay(err.message)); }
  };
  $('#share-copy').onclick = () => copy(shareLink());
  $('#share-yt').onclick = () => copy(ytLink(id, now));
  if ($('#share-send')) $('#share-send').onclick = () => navigator.share({title: v.title, url: shareLink()}).catch(() => {});
  function seek(ms) {
    now = ms; $('#frame').src = embed(id, ms); $('#yt').href = ytLink(id, ms); shareText();
    history.replaceState(null, '', `#/v/${id}?t=${ms}&q=${encodeURIComponent(q)}`);
    mark(true);
  }
  $('#main').onclick = e => { const b = e.target.closest('[data-seek]'); if (b) seek(+b.dataset.seek); };
  const step = d => { if (!hitTimes.length) return; const n = d > 0 ? (hitTimes.find(x => x > now) ?? hitTimes[0]) : ([...hitTimes].reverse().find(x => x < now) ?? hitTimes.at(-1)); seek(n); };
  if ($('#prev')) { $('#prev').onclick = () => step(-1); $('#next').onclick = () => step(1); }
  $('#find').addEventListener('input', e => lines(e.target.value));
  lines('');
  if (t) { window.scrollTo(0, 0); mark(true, 'instant'); }      // opened at a moment (a search hit, a chat answer): show its line
}

/* ---------- library ---------- */
let openSource = null, editing = null;
async function viewLibrary() {
  const {sources, worker} = await api('/api/sources');
  const totalV = sources.reduce((a, s) => a + (s.ready || 0), 0), totalS = sources.reduce((a, s) => a + (s.seconds || 0), 0);
  const range = s => [s.date_from || '…', s.date_to || '…'].join(' → ') + (s.max_videos ? ` · ≤${s.max_videos}` : '');
  const state = s => s.paused ? '<span class="pill warn">Paused</span>'
    : s.state === 'error' ? `<span class="pill bad" title="${esc(s.error)}">Error</span>`
    : ['listing', 'new', 'more'].includes(s.state) ? '<span class="pill run">Listing</span>'
    : s.waiting ? `<span class="pill q">${s.waiting} waiting</span>` : '<span class="pill ok">Done</span>';
  $('#main').innerHTML = `
    <div class="lib-head"><h2>Library</h2><span class="mono muted">${sources.length} sources · ${totalV} videos · ${hours(totalS)}</span></div>
    <div class="tablewrap"><table class="lib">
      <thead><tr><th>Source</th><th>Language</th><th>Range</th><th class="num">Videos</th><th>Searchable</th><th class="num">Whisper</th><th class="num">Errors</th><th>State</th><th></th></tr></thead>
      <tbody>${sources.map(s => {
        const pct = s.videos ? Math.round(100 * (s.ready || 0) / s.videos) : 0;
        return `<tr data-src="${s.id}" class="${openSource === s.id ? 'open' : ''}">
          <td><button class="linkish sname" data-open="${s.id}" dir="auto">${esc(s.title || s.url)}</button><div class="sub">${esc(s.kind || '')}</div></td>
          <td>${s.lang === 'auto' ? 'Detect' : LANG[s.lang]}</td>
          <td class="mono">${range(s)}</td>
          <td class="num">${s.videos || 0}</td>
          <td>${s.ready || 0} · ${hours(s.seconds || 0)}<div class="minibar"><b style="width:${pct}%"></b></div></td>
          <td class="num">${s.whisper || 0}</td>
          <td class="num">${s.errors || 0}</td>
          <td>${state(s)}</td>
          <td class="actions"><button class="icon" data-pause="${s.id}" data-paused="${s.paused ? 1 : 0}" title="${s.paused ? 'Resume' : 'Pause'}" aria-label="${s.paused ? 'Resume' : 'Pause'}">${s.paused ? PLAY : PAUSE}</button><button class="icon" data-refresh="${s.id}" title="Check now" aria-label="Check now">↻</button><a class="icon" href="/api/sources/${s.id}/export?format=txt" download title="Export" aria-label="Export">⤓</a><button class="icon" data-edit="${s.id}" title="Edit" aria-label="Edit">✎</button><button class="icon" data-del="${s.id}" title="Delete" aria-label="Delete">✕</button></td>
        </tr>${openSource === s.id ? `<tr class="vlist"><td colspan="9" id="vlist">…</td></tr>` : ''}`;
      }).join('')}</tbody></table></div>
    <section class="add">
      <h3>${editing ? 'Edit' : 'Add'}</h3>
      <form class="addf" id="addf">
        <label>Channel, playlist or video<input type="text" inputmode="url" autocomplete="off" spellcheck="false" id="f-url" required placeholder="https://www.youtube.com/@…" dir="ltr"></label>
        <label>Language<select id="f-lang"><option value="auto">Detect</option><option value="he">עברית</option><option value="en">English</option></select></label>
        <label>From<input type="date" id="f-from"></label>
        <label>To<input type="date" id="f-to"></label>
        <label>Max<input type="number" id="f-max" min="1" placeholder="∞"></label>
        <button class="btn primary" type="submit">${editing ? 'Save' : 'Add'}</button>
      </form>
    </section>`;
  if (editing) {
    const s = sources.find(x => x.id === editing);
    if (s) { $('#f-url').value = s.url; $('#f-url').disabled = true; $('#f-lang').value = s.lang; $('#f-from').value = s.date_from || ''; $('#f-to').value = s.date_to || ''; $('#f-max').value = s.max_videos || ''; }
  }
  $('#addf').addEventListener('submit', async e => {
    e.preventDefault();
    const body = {url: $('#f-url').value.trim(), lang: $('#f-lang').value, date_from: $('#f-from').value || null, date_to: $('#f-to').value || null, max_videos: +$('#f-max').value || null};
    try {
      if (editing) { await api(`/api/sources/${editing}`, {method: 'PATCH', body: JSON.stringify(body)}); editing = null; toast('Saved'); }
      else { await api('/api/sources', {method: 'POST', body: JSON.stringify(body)}); toast('Added'); }
      viewLibrary(); pollWorker();
    } catch (err) { toast({exists: 'Already in the library', link: 'Not a YouTube link'}[err.message] || err.message); }
  });
  if (openSource) loadVideos(openSource);
}

/* ---------- settings: your account, and for the owner (or the tailnet) people and requests ---------- */
const SAY = {exists: 'Already on the list', email: 'Check the email', taken: 'Username taken', username: 'Username: 2–32 of a–z, 0–9, . _ -',
  short: 'Passwords are at least 8 characters', long: 'That password is too long', current: 'Current password is wrong', mail: "Couldn't send the email",
  throttled: 'Too many. Try later.', owner: "That's the only owner", match: "The two don't match"};
const say = m => SAY[m] || m;
const when = t => t ? new Date(t * 1000).toLocaleDateString(undefined, {day: 'numeric', month: 'short', year: 'numeric'}) : '';
let pwMode = '';
async function viewSettings() {
  ME = await api('/api/me'); showMe();
  const [ppl, {shares}, cset] = await Promise.all([ME.admin ? api('/api/people') : null, api('/api/shares'), ME.admin ? api('/api/chat/settings') : null]);
  $('#main').innerHTML = `
    <div class="lib-head"><h2>Settings</h2></div>
    ${ME.email ? accountHTML() : ''}
    ${lookHTML()}
    ${cset ? chatSetHTML(cset) : ''}
    ${ppl ? peopleHTML(ppl) : ''}
    ${shares.length ? `<section class="add set"><h3>Shared links</h3><div class="tablewrap"><table class="lib ppl"><tbody>${shares.map(x => `<tr>
      <td><a href="#/v/${esc(x.video_id)}"><bdi>${esc(x.title || x.video_id)}</bdi></a><div class="sub"><bdi>${esc(x.channel || '')}</bdi></div></td>
      ${ME.admin ? `<td class="mono">${esc(x.made_by || '')}</td>` : ''}
      <td class="mono muted">${when(x.made_at)}</td>
      <td class="actions"><div class="acts"><button class="btn small" data-copy="${esc(x.url)}">Copy</button><button class="icon" data-unshare="${esc(x.token)}" title="Stop sharing" aria-label="Stop sharing">✕</button></div></td>
    </tr>`).join('')}</tbody></table></div></section>` : ''}`;
  wireSettings(ppl);
  wireLook();
  if (cset) wireChatSet(cset);
  const signin = parseHash().params.get('chatgpt');              // back from ChatGPT's sign-in, when it didn't finish
  if (signin) { history.replaceState(null, '', '#/settings'); toast(chatSay('signin-' + signin)); }
}
// The theme is per device (themes.js keeps it), so it's here for everyone, the tailnet too.
function lookHTML() {
  const TH = window.TamlilThemes, cur = TH.get();
  return `<section class="add set" id="lookset">
    <h3>Appearance</h3>
    <div class="setrow"><span class="lbl">Theme</span><select id="t-look">${TH.FAMILIES.map(f => `<option value="${f.id}" ${f.id === cur.look ? 'selected' : ''}>${esc(f.name)}</option>`).join('')}</select></div>
    <div class="setrow"><span class="lbl">Mode</span><div class="seg" role="group" aria-label="Mode">${[['auto', 'Auto'], ['light', 'Light'], ['dark', 'Dark']].map(([v, l]) =>
      `<button type="button" data-mode="${v}" aria-pressed="${cur.mode === v}">${l}</button>`).join('')}</div></div>
  </section>`;
}
function wireLook() {
  const TH = window.TamlilThemes;
  $('#t-look').onchange = e => TH.set({look: e.target.value});
  $$('[data-mode]').forEach(b => b.onclick = () => {
    TH.set({mode: b.dataset.mode});
    $$('[data-mode]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
  });
}
// Chat's settings: on or off, the model, who may use it, and the connections the models come from.
let chatForm = null;          // the connection form that's open: 'new', or a connection's id
let chatPick = null;          // the connection whose models are listed, while the list is open
function chatSetHTML(s) {
  const seg = (key, opts, cur) => `<div class="seg" role="group">${opts.map(([v, l]) => `<button type="button" data-cset="${key}" data-v="${v}" aria-pressed="${cur === v}">${l}</button>`).join('')}</div>`;
  const P = s.presets;
  return `<section class="add set" id="chatset">
    <div class="lib-head"><h3>Chat</h3>${s.on && !s.ready ? '<span class="pill warn">No model</span>' : ''}</div>
    <div class="setrow"><span class="lbl">Chat</span>${seg('on', [['0', 'Off'], ['1', 'On']], s.on ? '1' : '0')}</div>
    <div class="setrow"><span class="lbl">Model</span><button type="button" class="btn small" id="c-pick" ${s.connections.length ? '' : 'disabled'}>${esc(s.model_label || 'Choose')}</button></div>
    <div id="c-picker" hidden></div>
    <div class="setrow"><span class="lbl">Who</span>${seg('everyone', [['0', 'Just me'], ['1', 'Everyone']], s.everyone ? '1' : '0')}</div>
    ${s.month.answers ? `<div class="setrow"><span class="lbl">This month</span><span class="mono">${s.month.answers} answers${s.month.cost ? ` · $${s.month.cost.toFixed(2)}` : ''}</span></div>` : ''}
    <h4>Connections</h4>
    <div class="conns">${s.connections.map(c => `<div class="conn">
      <div class="grow"><b>${esc(c.name)}</b><div class="sub mono">${[P[c.preset]?.name !== c.name ? P[c.preset]?.name : '', c.key, c.base_url].filter(Boolean).map(esc).join(' · ')}</div></div>
      <button type="button" class="btn small" data-cedit="${c.id}">Edit</button><button type="button" class="icon" data-cdel="${c.id}" title="Remove" aria-label="Remove">✕</button>
    </div>${chatForm === c.id ? connFormHTML(s, c) : ''}`).join('')}</div>
    ${chatForm === 'new' ? connFormHTML(s, null) : '<div class="setrow"><button type="button" class="btn small" id="c-add">Add</button></div>'}
  </section>`;
}
function connFormHTML(s, c, preset) {
  preset = c ? c.preset : preset || 'claude_code';
  const p = s.presets[preset];
  const signedIn = s.connections.some(x => x.preset === 'chatgpt');
  const services = `<label>Service<select name="preset">${Object.entries(s.presets).filter(([k]) => k !== 'chatgpt' || !signedIn)
    .map(([k, x]) => `<option value="${k}" ${k === preset ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}</select></label>`;
  if (!c && preset === 'chatgpt') return `<form class="setf connf" id="c-form" data-preset="chatgpt">
    ${services}
    <div class="pwbtns" id="c-start"><button class="btn primary" type="button" id="c-gpt">Continue with ChatGPT</button><button class="btn" type="button" id="c-cancel">Cancel</button></div>
    <label class="wide" id="c-paste" hidden>Address from the ChatGPT tab<input type="url" name="callback" dir="ltr" spellcheck="false" autocomplete="off"></label>
    <div class="pwbtns" id="c-connect" hidden><button class="btn primary" type="submit">Connect</button><button class="btn" type="button" data-cancel>Cancel</button></div>
  </form>`;
  return `<form class="setf connf" id="c-form" data-preset="${preset}">
    ${c ? '' : services}
    <label>Name<input type="text" name="name" value="${esc(c ? c.name : p.name)}" maxlength="40"></label>
    ${['key', 'token', 'optional'].includes(p.key) ? `<label>${p.key === 'token' ? 'Token' : 'Key'}<input type="password" name="api_key" autocomplete="off" spellcheck="false" dir="ltr" placeholder="${esc(c?.key || '')}" ${!c && (p.key === 'key' || p.key === 'token') ? 'required' : ''}></label>` : ''}
    ${p.base_url !== null ? `<label>Address<input type="url" name="base_url" value="${esc(c ? c.base_url : p.base_url)}" dir="ltr" spellcheck="false" required></label>` : ''}
    <div class="pwbtns"><button class="btn primary" type="submit">Save</button><button class="btn" type="button" id="c-cancel">Cancel</button></div>
  </form>`;
}
function wireChatSet(s) {
  const fail = err => { toast(chatSay(err.message === 'token' ? 'token_' : err.message)); return null; };
  const save = async body => {
    try { const r = await api('/api/chat/settings', {method: 'POST', body: JSON.stringify(body)}); await viewSettings(); return r; }
    catch (err) { return fail(err); }
  };
  $$('[data-cset]').forEach(b => b.onclick = () => {
    const k = b.dataset.cset, v = b.dataset.v === '1';
    save({[k]: v}).then(r => r && k === 'everyone' && toast('Saved'));
  });
  const add = $('#c-add'); if (add) add.onclick = () => { chatForm = 'new'; viewSettings(); };
  $$('[data-cedit]').forEach(b => b.onclick = () => { chatForm = +b.dataset.cedit; viewSettings(); });
  $$('[data-cdel]').forEach(b => b.onclick = async () => {
    if (!b.dataset.armed) {
      b.dataset.armed = '1'; b.textContent = 'Remove?'; b.classList.add('pill', 'bad');
      setTimeout(() => { if (b.isConnected) { delete b.dataset.armed; b.textContent = '✕'; b.classList.remove('pill', 'bad'); } }, 4000);
      return;
    }
    await api(`/api/chat/connections/${b.dataset.cdel}`, {method: 'DELETE'}); toast('Removed'); viewSettings();
  });
  wireConnForm(s, fail);
  $('#c-pick').onclick = () => { chatPick = chatPick ? null : (+String(s.model).split('/')[0] || s.connections[0].id); viewSettings(); };
  if (chatPick && s.connections.some(c => c.id === chatPick)) openPicker(s, chatPick, save);
  else chatPick = null;
}
function wireConnForm(s, fail) {
  const f = $('#c-form');
  if (!f) return;
  const svc = f.querySelector('[name=preset]');
  if (svc) svc.onchange = () => { f.outerHTML = connFormHTML(s, null, svc.value); wireConnForm(s, fail); $('#c-form [name=preset]').focus(); };
  f.querySelectorAll('#c-cancel,[data-cancel]').forEach(b => b.onclick = () => { chatForm = null; viewSettings(); });
  const gpt = $('#c-gpt');
  if (gpt) gpt.onclick = async () => {
    const tab = window.open('about:blank', '_blank');            // opened now, while it's still the click
    try {
      const {url} = await api('/api/chat/chatgpt/start', {method: 'POST'});
      if (tab) { tab.opener = null; tab.location.href = url; } else window.open(url, '_blank', 'noopener');
      $('#c-start').hidden = true; $('#c-paste').hidden = false; $('#c-connect').hidden = false;
      f.querySelector('[name=callback]').focus();
    } catch (err) { if (tab) tab.close(); fail(err); }
  };
  f.onsubmit = async e => {
    e.preventDefault();
    if (f.dataset.preset === 'chatgpt' && chatForm === 'new') {
      try {
        const r = await api('/api/chat/chatgpt/finish', {method: 'POST', body: JSON.stringify({url: f.querySelector('[name=callback]').value})});
        chatForm = null;
        toast('Connected');
        if (!r.model) chatPick = r.added;
        await viewSettings();
      } catch (err) { fail(err); }
      return;
    }
    const body = {};
    for (const el of f.elements) if (el.name && (el.name !== 'api_key' || el.value.trim())) body[el.name] = el.value;
    try {
      const r = chatForm === 'new'
        ? await api('/api/chat/connections', {method: 'POST', body: JSON.stringify(body)})
        : await api(`/api/chat/connections/${chatForm}`, {method: 'PATCH', body: JSON.stringify(body)});
      chatForm = null;
      toast('Saved');
      if (r.added && !r.model) chatPick = r.added;          // nothing chosen yet: choose from this one's models
      await viewSettings();
    } catch (err) { fail(err); }
  };
}
async function openPicker(s, cid, save) {
  const box = $('#c-picker');
  const cur = String(s.model);
  box.hidden = false;
  box.innerHTML = `<div class="cpick">
    ${s.connections.length > 1 ? `<select id="cp-conn" aria-label="Connection">${s.connections.map(c => `<option value="${c.id}" ${c.id === cid ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</select>` : ''}
    <div class="cprow"><input type="search" id="cp-q" placeholder="Model" dir="ltr" spellcheck="false" autocomplete="off"><button type="button" class="btn small" id="cp-use">Use</button></div>
    <div class="cplist" id="cp-list"><div class="muted cpnote">…</div></div>
  </div>`;
  const q = $('#cp-q'), list = $('#cp-list');
  const pick = (id, name) => { chatPick = null; save({model: `${cid}/${id}`, model_name: name || ''}).then(r => r && toast('Saved')); };
  const conn = $('#cp-conn'); if (conn) conn.onchange = () => { chatPick = +conn.value; openPicker(s, chatPick, save); };
  $('#cp-use').onclick = () => q.value.trim() && pick(q.value.trim());
  q.onkeydown = e => { if (e.key === 'Enter' && q.value.trim()) { e.preventDefault(); pick(q.value.trim()); } };
  q.focus();
  let all;
  try { all = (await api(`/api/chat/connections/${cid}/models`)).models; }
  catch (err) { list.innerHTML = `<div class="cerr cpnote">${esc(chatSay(err.message))}</div>`; return; }
  const draw = () => {
    const w = q.value.trim().toLowerCase();
    const hits = all.filter(m => !w || m.id.toLowerCase().includes(w) || (m.name || '').toLowerCase().includes(w)).slice(0, 200);
    list.innerHTML = hits.map(m => `<button type="button" data-mid="${esc(m.id)}" data-mname="${esc(m.name || '')}" class="${`${cid}/${m.id}` === cur ? 'on' : ''}">
      <span>${esc(m.name || m.id)}</span>${m.name && m.name !== m.id ? `<span class="id">${esc(m.id)}</span>` : ''}</button>`).join('') || '<div class="muted cpnote">—</div>';
    list.querySelectorAll('[data-mid]').forEach(b => b.onclick = () => pick(b.dataset.mid, b.dataset.mname));
  };
  q.oninput = draw;
  draw();
}
function accountHTML() {
  return `<section class="add set">
    <h3>Account</h3>
    <form class="setf" id="me-f">
      <label>Name<input type="text" id="m-name" value="${esc(ME.name || '')}" maxlength="60" autocomplete="name" dir="auto"></label>
      <label>Username<input type="text" id="m-user" value="${esc(ME.username || '')}" maxlength="32" autocomplete="username" autocapitalize="none" spellcheck="false" required></label>
      <label>Email<input type="email" value="${esc(ME.email)}" disabled dir="ltr"></label>
      <button class="btn primary" type="submit">Save</button>
    </form>
    <div class="setrow">
      <span class="lbl">Password</span>${ME.password ? '<span class="pill ok">On</span>' : '<span class="pill q">Off</span>'}
      <button class="btn small" data-pw="set">${ME.password ? 'Change password' : 'Set a password'}</button>
      ${ME.password ? '<button class="linkish dim" data-pw="remove">Remove password</button>' : ''}
    </div>
    <form class="setf pwf" id="pw-f" ${pwMode ? '' : 'hidden'}>
      <input type="text" autocomplete="username" value="${esc(ME.username || ME.email)}" hidden>
      ${ME.password ? '<label>Current password<input type="password" id="pw-cur" autocomplete="current-password" required></label>' : ''}
      ${pwMode === 'remove' ? '' : `<label>New password<input type="password" id="pw-new" autocomplete="new-password" minlength="8" required></label>
      <label>Again<input type="password" id="pw-again" autocomplete="new-password" minlength="8" required></label>`}
      <div class="pwbtns"><button class="btn ${pwMode === 'remove' ? 'danger' : 'primary'}" type="submit">${pwMode === 'remove' ? 'Remove' : 'Save'}</button><button class="btn" type="button" id="pw-cancel">Cancel</button></div>
    </form>
    <div class="setrow">
      <button class="btn small" id="out-others">Sign out everywhere else</button>
      <button class="btn small" id="out">Sign out</button>
    </div>
  </section>`;
}
function peopleHTML({people, requests, settings, mail, join}) {
  return `<section class="add set" id="people">
    <div class="lib-head"><h3>People</h3>${mail ? '' : '<span class="pill warn">No email</span>'}</div>
    ${requests.length ? `<h4>Requests <span class="badge">${requests.length}</span></h4><div class="tablewrap"><table class="lib ppl reqs"><tbody>${requests.map(r => `<tr>
      <td><b dir="auto">${esc(r.name)}</b><div class="sub">${esc(r.email)}</div></td>
      <td class="mono">${esc(r.username || '')}</td>
      <td class="note"><bdi>${esc(r.note || '')}</bdi></td>
      <td class="mono muted">${when(r.at)}</td>
      <td class="actions"><div class="acts"><button class="btn small" data-no="${esc(r.email)}">Decline</button><button class="btn small primary" data-yes="${esc(r.email)}">Approve</button></div></td>
    </tr>`).join('')}</tbody></table></div>` : ''}
    ${people.length ? `<div class="tablewrap"><table class="lib ppl"><tbody>${people.map(p => `<tr>
      <td>${p.name ? `<b dir="auto">${esc(p.name)}</b><div class="sub">${esc(p.email)}</div>` : esc(p.email)}</td>
      <td class="mono">${esc(p.username || '')}</td>
      <td>${p.owner ? '<span class="pill ok">Owner</span> ' : ''}${p.joined ? '' : '<span class="pill q">Invited</span>'}</td>
      <td class="mono muted">${when(p.joined || p.added)}</td>
      <td class="actions"><div class="acts">${!p.joined && mail ? `<button class="btn small" data-reinvite="${esc(p.email)}">Send again</button>` : ''}${p.owner ? '' : `<button class="icon" data-unperson="${esc(p.email)}" title="Remove" aria-label="Remove">✕</button>`}</div></td>
    </tr>`).join('')}</tbody></table></div>` : ''}
    <form class="addf pplf" id="pplf">
      <label>Email<input type="email" id="p-email" required autocomplete="off" dir="ltr"></label>
      <label>Name<input type="text" id="p-name" autocomplete="off" maxlength="60" dir="auto"></label>
      <button class="btn primary" type="submit">Invite</button>
    </form>
    <h4>Invite requests</h4>
    <div class="setrow">
      <span class="lbl">Requests</span>
      <div class="seg" role="group" aria-label="Requests"><button type="button" data-set="requests" data-v="1" aria-pressed="${settings.requests}">Open</button><button type="button" data-set="requests" data-v="0" aria-pressed="${!settings.requests}">Closed</button></div>
      ${settings.requests ? `<span class="mono muted joinurl">${esc(join.replace(/^https?:\/\//, ''))}</span><button class="btn small" data-copy="${esc(join)}">Copy</button>` : ''}
    </div>
    <div class="setrow">
      <span class="lbl">Email me</span>
      <div class="seg" role="group" aria-label="Email me"><button type="button" data-set="notify" data-v="1" aria-pressed="${settings.notify}">On</button><button type="button" data-set="notify" data-v="0" aria-pressed="${!settings.notify}">Off</button></div>
    </div>
  </section>`;
}
function wireSettings(ppl) {
  const f = $('#me-f');
  if (f) {
    f.addEventListener('submit', async e => {
      e.preventDefault();
      try { await api('/api/me', {method: 'POST', body: JSON.stringify({name: $('#m-name').value, username: $('#m-user').value.trim()})}); toast('Saved'); viewSettings(); }
      catch (err) { toast(say(err.message)); }
    });
    $('#pw-f').addEventListener('submit', async e => {
      e.preventDefault();
      const current = $('#pw-cur') ? $('#pw-cur').value : null;
      try {
        if (pwMode === 'remove') await api('/api/me/password/remove', {method: 'POST', body: JSON.stringify({current})});
        else {
          if ($('#pw-new').value !== $('#pw-again').value) { toast(say('match')); return; }
          await api('/api/me/password', {method: 'POST', body: JSON.stringify({password: $('#pw-new').value, current})});
        }
        toast(pwMode === 'remove' ? 'Removed' : 'Saved'); pwMode = ''; viewSettings();
      } catch (err) { toast(say(err.message)); }
    });
    $('#pw-cancel').onclick = () => { pwMode = ''; viewSettings(); };
    $('#out-others').onclick = async () => { await api('/api/me/signout-others', {method: 'POST'}); toast('Signed out everywhere else'); };
    $('#out').onclick = async () => { await fetch('/api/auth/logout', {method: 'POST'}); location.href = '/login'; };
  }
  if (ppl) $('#pplf').addEventListener('submit', async e => {
    e.preventDefault();
    try {
      const r = await api('/api/people', {method: 'POST', body: JSON.stringify({email: $('#p-email').value.trim(), name: $('#p-name').value.trim() || null})});
      toast(r.invited ? 'Invited' : 'Added'); viewSettings();
    } catch (err) { toast(say(err.message)); }
  });
}
document.addEventListener('click', async e => {
  const t = e.target.closest('[data-pw],[data-yes],[data-no],[data-reinvite],[data-set],[data-copy],[data-unshare]');
  if (!t || !$('.set')) return;
  try {
    if (t.dataset.pw) { pwMode = t.dataset.pw; await viewSettings(); ($('#pw-cur') || $('#pw-new')).focus(); }
    else if (t.dataset.yes) { const r = await api(`/api/requests/${encodeURIComponent(t.dataset.yes)}/yes`, {method: 'POST'}); toast(r.mailed ? 'Approved' : 'Approved · no email'); viewSettings(); }
    else if (t.dataset.no) { await api(`/api/requests/${encodeURIComponent(t.dataset.no)}/no`, {method: 'POST'}); toast('Declined'); viewSettings(); }
    else if (t.dataset.reinvite) { await api(`/api/people/${encodeURIComponent(t.dataset.reinvite)}/invite`, {method: 'POST'}); toast('Sent'); }
    else if (t.dataset.set) { await api('/api/settings', {method: 'POST', body: JSON.stringify({[t.dataset.set]: t.dataset.v === '1'})}); viewSettings(); }
    else if (t.dataset.copy) copy(t.dataset.copy);
    else if (t.dataset.unshare) { await api(`/api/shares/${encodeURIComponent(t.dataset.unshare)}`, {method: 'DELETE'}); toast('Stopped'); viewSettings(); }
  } catch (err) { toast(say(err.message)); }
});
document.addEventListener('click', e => {           // a result's channel: only that channel
  const c = e.target.closest('.chan[data-src]');
  if (c) go(searchHash({src: c.dataset.src}));
});
document.addEventListener('click', async e => {
  const t = e.target.closest('[data-unperson]');
  if (!t) return;
  if (t.dataset.armed) {
    try { await api(`/api/people/${encodeURIComponent(t.dataset.unperson)}`, {method: 'DELETE'}); toast('Removed'); }
    catch (err) { toast(say(err.message)); }
    viewSettings();
  } else { t.dataset.armed = '1'; t.textContent = 'Remove?'; t.classList.add('pill', 'bad'); setTimeout(() => { if (t.isConnected) { delete t.dataset.armed; t.textContent = '✕'; t.classList.remove('pill', 'bad'); } }, 4000); }
});

async function loadVideos(id) {
  const {videos} = await api(`/api/sources/${id}/videos`);
  const st = v => v.state === 'ready' ? `<span class="src src-${v.origin}">${ORIGIN[v.origin]}</span>`
    : v.state === 'error' ? `<span class="pill bad">Error</span> <button class="btn small" data-retry="${v.id}">Retry</button><div class="err">${esc(v.error)}</div>`
    : v.state === 'transcribing' ? '<span class="pill run">Whisper</span>' : `<span class="pill q">${esc(v.state)}</span>`;
  const el = $('#vlist'); if (!el) return;
  el.innerHTML = videos.length ? `<table><tbody>${videos.map(v => `<tr>
      <td class="mono">${day(v.upload_date)}</td><td dir="auto">${v.state === 'ready' ? `<a href="#/v/${v.id}">${esc(v.title || v.id)}</a>` : esc(v.title || v.id)}</td>
      <td class="mono num">${v.duration ? fmt(v.duration * 1000) : ''}</td><td>${LANG[v.lang] || ''}</td><td>${st(v)}</td></tr>`).join('')}</tbody></table>` : '<span class="muted">0</span>';
}
document.addEventListener('click', async e => {
  const t = e.target.closest('[data-open],[data-refresh],[data-edit],[data-del],[data-retry],[data-pause]');
  if (!t || !$('.lib')) return;
  if (t.dataset.pause) {
    const off = t.dataset.paused === '1';
    await api(`/api/sources/${t.dataset.pause}/pause`, {method: 'POST', body: JSON.stringify({paused: !off})});
    toast(off ? 'Resumed' : 'Paused'); viewLibrary(); pollWorker();
  }
  else if (t.dataset.open) { openSource = openSource === +t.dataset.open ? null : +t.dataset.open; viewLibrary(); }
  else if (t.dataset.refresh) { await api(`/api/sources/${t.dataset.refresh}/refresh`, {method: 'POST'}); toast('Queued'); viewLibrary(); }
  else if (t.dataset.edit) { editing = +t.dataset.edit; await viewLibrary(); $('#addf').scrollIntoView({behavior: 'smooth'}); }
  else if (t.dataset.del) {
    if (t.dataset.armed) { await api(`/api/sources/${t.dataset.del}`, {method: 'DELETE'}); toast('Deleted'); viewLibrary(); }
    else { t.dataset.armed = '1'; t.textContent = 'Delete?'; t.classList.add('pill', 'bad'); setTimeout(() => { if (t.isConnected) { delete t.dataset.armed; t.textContent = '✕'; t.classList.remove('pill', 'bad'); } }, 4000); }
  }
  else if (t.dataset.retry) { await api(`/api/videos/${t.dataset.retry}/retry`, {method: 'POST'}); toast('Queued'); loadVideos(openSource); }
});

/* ---------- chat: questions about the transcripts, answered by Claude ---------- */
const CHAT_SAY = {off: 'Chat is off', day: "That's all for today", key: "The key didn't work",
  token: "The Claude Code token didn't work", limit: 'Too many requests. Try again in a minute.', model: "That model isn't available",
  credit: 'The account is out of credit', plan: 'The plan is out of usage', signin: 'Sign in to ChatGPT again', 'signin-scope': 'Plan usage not granted',
  'signin-start': 'Start again', 'signin-state': 'Start again', 'signin-expired': 'Start again', refused: 'No answer to this one',
  long: 'That took too many steps', down: "Couldn't reach the model", network: "Couldn't reach the model", claude: "Claude Code didn't start",
  request: "The model couldn't take that", tools: "This model can't search", 'too-long': 'That question is too long', missing: 'Not found', video: 'Not found',
  chat: 'Chat is off', preset: 'Choose a service', address: "That address doesn't look right", api_key: "That doesn't look like a key", token_: "That doesn't look like a token"};
const chatSay = m => CHAT_SAY[m] || (String(m).startsWith('signin-') ? 'Not connected' : m);
const DOINGS = {search: 'Searching', read: 'Reading', list: 'Listing videos'};
const CITE = /^#([A-Za-z0-9_-]{1,20})@(\d+(?::\d{1,2}){0,2})$/;
const tsMs = t => t.split(':').reduce((a, x) => a * 60 + +x, 0) * 1000;
// The answer being written. It lives here, not in the page, so it carries on while you look at other
// screens, and shows up again (still writing, or finished) when you come back to its chat.
const CH = {ctrl: null, chat: null, question: '', draft: '', status: '', err: ''};
const viewing = () => { const {parts} = parseHash(); return parts[0] === 'chat' ? +(parts[1] || 0) : -1; };
const liveHTML = () => `<div class="msg ai live" id="live"><div class="status">${CH.status || '<span class="dot"></span>'}</div><div class="draft"></div>${CH.err}</div>`;
function paintLive() {
  const el = $('#live');
  if (!el) return;
  const stick = window.innerHeight + window.scrollY >= document.body.scrollHeight - 120;
  el.querySelector('.status').innerHTML = CH.status || '<span class="dot"></span>';
  const out = el.querySelector('.draft'); out.dir = mainDir(CH.draft); out.innerHTML = md(CH.draft, {});
  if (stick) window.scrollTo(0, document.body.scrollHeight);
}

function inline(s, refs) {                // s is escaped already
  return s.replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, txt, url) => {
      const c = url.match(CITE);
      if (c) { const r = refs && refs[c[1]]; return `<a class="cite" dir="ltr" href="#/v/${c[1]}?t=${tsMs(c[2])}"${r ? ` title="${esc(r.title)}"` : ''}>${txt}</a>`; }
      return /^https?:\/\//.test(url) ? `<a href="${url}" target="_blank" rel="noopener noreferrer">${txt}</a>` : txt;
    })
    .replace(/\(((?:\s*<a class="cite"[^>]*>[^<]*<\/a>\s*[,;]?)+)\)/g, '$1')     // a moment needs no brackets around it
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/(^|[^*\w])\*([^*\s][^*]*?)\*(?!\w)/g, '$1<i>$2</i>');
}
// One direction for a whole answer, by the letters most of it is in: an English answer that names a
// Hebrew lecture stays left to right, and a Hebrew one that quotes English stays right to left.
const mainDir = s => (s.match(/[א-ת]/g) || []).length > (s.match(/[A-Za-z]/g) || []).length ? 'rtl' : 'ltr';
function md(text, refs) {                 // the little markdown Claude writes: paragraphs, lists, headings, quotes
  const out = []; let para = [], list = null;
  const flush = () => {
    if (para.length) { out.push(`<p>${para.map(l => inline(l, refs)).join('<br>')}</p>`); para = []; }
    if (list) { out.push(`<${list.tag}>${list.items.map(x => `<li>${inline(x, refs)}</li>`).join('')}</${list.tag}>`); list = null; }
  };
  for (const raw of esc(text).split('\n')) {
    const l = raw.trimEnd(); let m;
    if (!l.trim()) { flush(); continue; }
    if ((m = l.match(/^\s*[-*•]\s+(.*)$/)) || (m = l.match(/^\s*\d+[.)]\s+(.*)$/))) {
      const tag = /^\s*\d/.test(l) ? 'ol' : 'ul';
      if (para.length || (list && list.tag !== tag)) flush();
      list = list || {tag, items: []}; list.items.push(m[1]); continue;
    }
    if ((m = l.match(/^#{1,6}\s+(.*)$/))) { flush(); out.push(`<h4>${inline(m[1], refs)}</h4>`); continue; }
    if ((m = l.match(/^&gt;\s?(.*)$/))) { flush(); out.push(`<blockquote>${inline(m[1], refs)}</blockquote>`); continue; }
    if (list) flush();
    para.push(l);
  }
  flush();
  return out.join('');
}
function refsHTML(refs, text) {
  const seen = new Map();
  for (const m of (text || '').matchAll(/\]\(#([A-Za-z0-9_-]{1,20})@([\d:]+)\)/g)) if (refs[m[1]] && !seen.has(m[1])) seen.set(m[1], tsMs(m[2]));
  if (!seen.size) return '';
  return `<div class="refs">${[...seen].map(([id, ms]) => { const r = refs[id]; return `<a class="ref" href="#/v/${id}?t=${ms}">
    <span class="rthumb" style="background-image:url('${thumb(id)}')"></span><span dir="${dirOf(r.title)}"><bdi>${esc(r.title)}</bdi><small title="${day(r.upload_date)}">${esc(r.channel || '')}</small></span></a>`; }).join('')}</div>`;
}
const aiHTML = (text, refs, tail = '') => `<div class="msg ai"><div class="draft" dir="${mainDir(text)}">${md(text, refs)}</div>${refsHTML(refs, text)}${tail}</div>`;
const msgHTML = m => m.role === 'user'
  ? `<div class="msg me"><p dir="auto">${esc(m.text).replace(/\n/g, '<br>')}</p></div>`
  : aiHTML(m.text, m.refs || {});
function listHTML(chats, id) {
  return chats.map(x => `<li class="${x.id === id ? 'on' : ''}"><a href="#/chat/${x.id}"><bdi>${esc(x.title)}</bdi><small>${x.video_title
    ? `<bdi>${esc(x.video_title)}</bdi> · ` : x.source_title ? `<bdi>${esc(x.source_title)}</bdi> · ` : ''}${when(x.updated_at)}</small></a><button class="icon" data-delchat="${x.id}" title="Delete" aria-label="Delete">✕</button></li>`).join('');
}
async function streamAsk(chatId, text, onEvent, signal) {
  const r = await fetch(`/api/chats/${chatId}/ask`, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({text}), signal});
  if (r.status === 401) { location.href = '/login'; return; }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  const rd = r.body.getReader(), dec = new TextDecoder(); let buf = '';
  for (;;) {
    const {value, done} = await rd.read();
    if (done) break;
    buf += dec.decode(value, {stream: true});
    let i;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const raw = buf.slice(0, i); buf = buf.slice(i + 2);
      let ev = 'message', data = '';
      for (const line of raw.split('\n')) { if (line.startsWith('event: ')) ev = line.slice(7); else if (line.startsWith('data: ')) data += line.slice(6); }
      onEvent(ev, data ? JSON.parse(data) : {});
    }
  }
}
async function viewChat(id) {
  id = id ? +id : null;
  if (!ME.chat) {
    $('#main').innerHTML = `<div class="empty">${ME.admin ? '<a class="btn primary" href="#/settings">Set up chat</a>' : esc(chatSay('off'))}</div>`;
    return;
  }
  const [{chats}, c, src] = await Promise.all([api('/api/chats'), id ? api(`/api/chats/${id}`) : null, id ? null : api('/api/sources')]);
  const scope = c ? (c.video ? `<a class="scopev" href="#/v/${esc(c.video.id)}"><span class="rthumb" style="background-image:url('${thumb(c.video.id)}')"></span><span dir="${dirOf(c.video.title)}"><bdi>${esc(c.video.title)}</bdi><small><bdi>${esc(c.video.channel || '')}</bdi> · <span dir="ltr">${day(c.video.upload_date)}</span></small></span></a>`
      : c.source ? `<span class="pill q"><bdi>${esc(c.source.title)}</bdi></span>` : '')
    : `<select id="c-src" aria-label="Channel"><option value="">All channels</option>${src.sources.map(x => `<option value="${x.id}">${esc(x.title || x.url)}</option>`).join('')}</select>`;
  const busy = () => CH.ctrl && CH.chat === id;
  const msgs = c ? c.messages : [], mine = busy();
  // A question is saved once its answer starts; until then it's shown from here.
  const unsaved = mine && !(msgs.length && msgs.at(-1).role === 'user' && msgs.at(-1).text === CH.question);
  const has = msgs.length || mine;
  $('#main').innerHTML = `<div class="chat${has ? ' has-thread' : ''}">
    <aside class="clist"><a class="btn small primary" href="#/chat">New chat</a><ol id="clist">${listHTML(chats, id)}</ol></aside>
    <section class="cmain">
      <a class="cback" href="#/chat">← Chats</a>
      ${scope ? `<div class="cscope">${scope}</div>` : ''}
      <div class="thread" id="thread">${msgs.map(msgHTML).join('')}${unsaved ? msgHTML({role: 'user', text: CH.question}) : ''}${mine ? liveHTML() : ''}</div>
      <form class="askf" id="askf"><textarea id="askq" rows="1" dir="auto" placeholder="Ask" aria-label="Ask" maxlength="4000"></textarea><button class="btn primary" id="askb" type="submit">${mine ? 'Stop' : 'Ask'}</button></form>
    </section></div>`;
  if (mine) paintLive();
  const q = $('#askq'), form = $('#askf');
  const grow = () => { q.style.height = 'auto'; q.style.height = Math.min(q.scrollHeight, 240) + 'px'; };
  q.addEventListener('input', grow);
  // Enter sends; while an answer is being written it does nothing, so a typed follow-up waits for it.
  q.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); if (!busy()) form.requestSubmit(); } });
  if (has) requestAnimationFrame(() => window.scrollTo(0, document.body.scrollHeight));
  if (!matchMedia('(hover: none)').matches || !has) q.focus();
  form.addEventListener('submit', async e => {
    e.preventDefault();
    if (busy()) { CH.ctrl.abort(); fetch('/api/chats/stop', {method: 'POST'}).catch(() => {}); return; }
    const text = q.value.trim();
    if (!text) return;
    if (!id) {
      try { id = (await api('/api/chats', {method: 'POST', body: JSON.stringify({source_id: +$('#c-src').value || null})})).id; }
      catch (err) { toast(chatSay(err.message)); return; }
      history.replaceState(null, '', `#/chat/${id}`);
      const sel = $('#c-src'), name = sel.value ? sel.selectedOptions[0].textContent : '';
      sel.parentElement.innerHTML = name ? `<span class="pill q"><bdi>${esc(name)}</bdi></span>` : '';
    }
    const chatId = id, ctrl = new AbortController();
    Object.assign(CH, {ctrl, chat: chatId, question: text, draft: '', status: '', err: ''});
    q.value = ''; grow();
    $('.chat').classList.add('has-thread');
    $('#thread').insertAdjacentHTML('beforeend', msgHTML({role: 'user', text}) + liveHTML());
    window.scrollTo(0, document.body.scrollHeight);
    $('#askb').textContent = 'Stop';
    const current = () => CH.ctrl === ctrl;       // a newer question (in any chat) takes over from this one
    let raf = 0, final = null;
    const paint = () => { raf = 0; if (current()) paintLive(); };
    const fail = code => { CH.err += `<div class="cerr">${esc(chatSay(code))}</div>`; const el = $('#live'); if (el) el.insertAdjacentHTML('beforeend', `<div class="cerr">${esc(chatSay(code))}</div>`); };
    try {
      await streamAsk(chatId, text, (ev, d) => {
        if (!current()) return;
        if (ev === 'start') refreshChats();
        else if (ev === 'text') { CH.draft += d.t; if (!raf) raf = requestAnimationFrame(paint); }
        else if (ev === 'tool') { CH.draft = ''; CH.status = `<span class="dot"></span>${DOINGS[d.what] || ''} ${d.arg ? `<bdi>${esc(d.arg)}</bdi>` : ''}`; paintLive(); }
        else if (ev === 'reset') { CH.draft = ''; paintLive(); }
        else if (ev === 'error') fail(d.code);
        else if (ev === 'done') final = d;
      }, ctrl.signal);
    } catch (err) {
      if (err.name !== 'AbortError' && current()) fail(err.message);
    } finally {
      cancelAnimationFrame(raf);
      if (current()) {
        const el = $('#live'), said = final ? final.text : CH.draft.trim();
        if (el) el.outerHTML = said || CH.err ? aiHTML(said, final ? final.refs || {} : {}, CH.err) : '';
        Object.assign(CH, {ctrl: null, chat: null, question: '', draft: '', status: '', err: ''});
        if (viewing() === chatId && $('#askb')) $('#askb').textContent = 'Ask';
      }
      refreshChats();
    }
  });
}
const refreshChats = () => api('/api/chats').then(r => { const l = $('#clist'); if (l) l.innerHTML = listHTML(r.chats, viewing()); }).catch(() => {});
document.addEventListener('click', async e => {
  const t = e.target.closest('[data-delchat]');
  if (!t) return;
  e.preventDefault();
  if (!t.dataset.armed) {
    t.dataset.armed = '1'; t.textContent = 'Delete?'; t.classList.add('pill', 'bad');
    setTimeout(() => { if (t.isConnected) { delete t.dataset.armed; t.textContent = '✕'; t.classList.remove('pill', 'bad'); } }, 4000);
    return;
  }
  await api(`/api/chats/${t.dataset.delchat}`, {method: 'DELETE'});
  if (+(parseHash().parts[1] || 0) === +t.dataset.delchat) go('/chat'); else viewChat(parseHash().parts[1]);
});

/* ---------- worker status ---------- */
const DOING = {listing: 'Listing', captions: 'Captions', audio: 'Audio', transcribing: 'Whisper'};
async function pollWorker() {
  try {
    const {worker: w} = await api('/api/sources');
    const el = $('#worker'), stale = !w.at || Date.now() / 1000 - w.at > 180;
    el.className = 'worker' + (stale ? ' bad' : w.doing && w.doing !== 'idle' ? ' busy' : '');
    if (stale) el.textContent = 'Worker offline';
    else if (!w.doing || w.doing === 'idle') el.textContent = 'Idle';
    else if (w.doing === 'blocked') { el.className = 'worker bad'; el.textContent = `Blocked by YouTube until ${new Date(w.until * 1000).toLocaleTimeString([], {hour: 'numeric', minute: '2-digit'})}`; }
    else if (w.doing === 'switching') el.textContent = 'Changing VPN server';
    else if (w.doing === 'offline') { el.className = 'worker bad'; el.textContent = 'VPN down'; }
    else {
      const pct = w.doing === 'transcribing' && w.progress != null ? ` ${Math.round(w.progress * 100)}%` : '';
      el.textContent = `${DOING[w.doing] || w.doing}${pct} · `;
      const t = document.createElement('bdi'); t.textContent = w.title || ''; el.append(t);
    }
    el.title = w.title || '';
  } catch { /* the next poll tries again */ }
}

/* ---------- router ---------- */
async function route() {
  const {parts, params} = parseHash();
  const screen = parts[0] || 'search';
  $$('[data-nav]').forEach(a => a.setAttribute('aria-current', a.dataset.nav === (screen === 'v' ? 'search' : screen) ? 'page' : 'false'));
  $('#main').onclick = null;
  try {
    if (screen === 'v' && parts[1]) await viewVideo(parts[1], params);
    else if (screen === 'library') await viewLibrary();
    else if (screen === 'settings') await viewSettings();
    else if (screen === 'chat') await viewChat(parts[1]);
    else await viewSearch(params);
  } catch (err) { $('#main').innerHTML = `<div class="empty">${esc(err.message)}</div>`; }
  if (screen !== 'chat' && !(screen === 'v' && params.get('t'))) window.scrollTo(0, 0);   // a moment scrolls to its own line
}
document.addEventListener('keydown', e => { if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); go('/search'); setTimeout(() => $('#q')?.focus(), 50); } });
window.addEventListener('hashchange', route);
function showMe() {
  $('#me').textContent = ME.username || ''; $('#me').hidden = !ME.username;
  $('#waiting').textContent = ME.waiting || ''; $('#waiting').hidden = !ME.waiting;
  $('#nav-chat').hidden = !(ME.chat || ME.admin);
}
Promise.all([api('/api/config').then(c => { CFG = c; }), api('/api/me').then(m => { ME = m; })]).catch(() => {}).finally(() => {
  showMe(); route(); pollWorker(); setInterval(pollWorker, 5000);
});
})();
