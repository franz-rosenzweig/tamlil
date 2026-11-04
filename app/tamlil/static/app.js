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
const S = {q: '', lang: 'all'};
async function viewSearch(params) {
  S.q = params.get('q') || ''; S.lang = params.get('lang') || 'all';
  $('#main').innerHTML = `
    <form class="sbar" id="sform" role="search">
      <input type="search" id="q" dir="auto" autocomplete="off" value="${esc(S.q)}" placeholder="Search" aria-label="Search">
      <div class="seg" role="group" aria-label="Language">${[['all', 'All'], ['he', 'עברית'], ['en', 'English']].map(([k, l]) =>
        `<button type="button" data-lang="${k}" aria-pressed="${S.lang === k}">${l}</button>`).join('')}</div>
    </form>
    <div class="meta-line" id="qmeta"></div>
    <div class="results" id="results"></div>`;
  const input = $('#q');
  if (!S.q) input.focus();
  $('#sform').addEventListener('submit', e => { e.preventDefault(); go(`/search?q=${encodeURIComponent(input.value.trim())}&lang=${S.lang}`); });
  $$('[data-lang]').forEach(b => b.addEventListener('click', () => go(`/search?q=${encodeURIComponent(input.value.trim())}&lang=${b.dataset.lang}`)));
  if (!S.q) { await emptyState(); return; }
  $('#results').innerHTML = '<div class="empty">…</div>';
  const res = await api(`/api/search?q=${encodeURIComponent(S.q)}&lang=${S.lang}`);
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
      <div class="rmeta"><span dir="auto">${esc(v.channel)}</span><span>${day(v.upload_date)}</span><span class="src src-${v.origin}">${ORIGIN[v.origin] || ''}</span><span>${LANG[v.lang] || ''}</span></div>
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
        </div>
      </div>
    </div>
    <div class="tbar"><input type="search" id="find" dir="auto" placeholder="Find" aria-label="Find in transcript"><span class="count" id="tcount">${segs.length} lines</span></div>
    <ol class="tlines" id="tlines"></ol>`;
  const back = $('#back'); if (back) back.addEventListener('click', () => go(`/search?q=${encodeURIComponent(q)}&lang=${S.lang}`));
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
  function mark(scroll) {
    let cur = null;
    for (const li of $$('.tl')) { const on = +li.dataset.ms <= now; if (on) cur = li; li.classList.remove('now'); }
    if (cur) { cur.classList.add('now'); if (scroll) cur.scrollIntoView({block: 'center', behavior: 'smooth'}); }
    $$('.tk').forEach(k => k.classList.toggle('cur', +k.dataset.seek === now));
  }
  function seek(ms) {
    now = ms; $('#frame').src = embed(id, ms); $('#yt').href = ytLink(id, ms);
    history.replaceState(null, '', `#/v/${id}?t=${ms}&q=${encodeURIComponent(q)}`);
    mark(true);
  }
  $('#main').onclick = e => { const b = e.target.closest('[data-seek]'); if (b) seek(+b.dataset.seek); };
  const step = d => { if (!hitTimes.length) return; const n = d > 0 ? (hitTimes.find(x => x > now) ?? hitTimes[0]) : ([...hitTimes].reverse().find(x => x < now) ?? hitTimes.at(-1)); seek(n); };
  if ($('#prev')) { $('#prev').onclick = () => step(-1); $('#next').onclick = () => step(1); }
  $('#find').addEventListener('input', e => lines(e.target.value));
  lines('');
}

/* ---------- library ---------- */
let openSource = null, editing = null;
async function viewLibrary() {
  const {sources, worker} = await api('/api/sources');
  const totalV = sources.reduce((a, s) => a + (s.ready || 0), 0), totalS = sources.reduce((a, s) => a + (s.seconds || 0), 0);
  const range = s => [s.date_from || '…', s.date_to || '…'].join(' → ') + (s.max_videos ? ` · ≤${s.max_videos}` : '');
  const state = s => s.state === 'error' ? `<span class="pill bad" title="${esc(s.error)}">Error</span>`
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
          <td class="actions"><button class="icon" data-refresh="${s.id}" title="Check now">↻</button><button class="icon" data-edit="${s.id}" title="Edit">✎</button><button class="icon" data-del="${s.id}" title="Delete">✕</button></td>
        </tr>${openSource === s.id ? `<tr class="vlist"><td colspan="9" id="vlist">…</td></tr>` : ''}`;
      }).join('')}</tbody></table></div>
    <section class="add">
      <h3>${editing ? 'Edit' : 'Add'}</h3>
      <form class="addf" id="addf">
        <label>Channel, playlist or video<input type="url" id="f-url" required placeholder="https://www.youtube.com/@…" dir="ltr"></label>
        <label>Language<select id="f-lang"><option value="auto">Detect</option><option value="he">עברית</option><option value="en">English</option></select></label>
        <label>From<input type="date" id="f-from"></label>
        <label>To<input type="date" id="f-to"></label>
        <label>Max<input type="number" id="f-max" min="1" placeholder="∞"></label>
        <button class="btn primary" type="submit">${editing ? 'Save' : 'Add'}</button>
      </form>
    </section>
    ${ME.admin ? '<section class="add" id="people"></section>' : ''}`;
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
    } catch (err) { toast(err.message === 'exists' ? 'Already in the library' : err.message); }
  });
  if (openSource) loadVideos(openSource);
  if (ME.admin) viewPeople();
}

/* ---------- people (the owner, and the tailnet) ---------- */
async function viewPeople() {
  const {people, mail} = await api('/api/people');
  const el = $('#people'); if (!el) return;
  const when = t => t ? new Date(t * 1000).toLocaleDateString(undefined, {day: 'numeric', month: 'short', year: 'numeric'}) : '';
  el.innerHTML = `
    <div class="lib-head"><h3>People</h3>${mail ? '' : '<span class="pill warn">No email</span>'}</div>
    ${people.length ? `<div class="tablewrap"><table class="lib ppl"><tbody>${people.map(p => `<tr>
      <td>${esc(p.email)}</td>
      <td class="mono">${p.username ? esc(p.username) : '<span class="pill q">Invited</span>'}</td>
      <td>${p.owner ? '<span class="pill ok">Owner</span>' : ''}</td>
      <td class="mono muted">${when(p.joined || p.added)}</td>
      <td class="actions">${p.owner ? '' : `<button class="icon" data-unperson="${esc(p.email)}" title="Remove">✕</button>`}</td>
    </tr>`).join('')}</tbody></table></div>` : ''}
    <form class="addf pplf" id="pplf">
      <label>Email<input type="email" id="p-email" required autocomplete="off" dir="ltr"></label>
      <button class="btn primary" type="submit">Invite</button>
    </form>`;
  $('#pplf').addEventListener('submit', async e => {
    e.preventDefault();
    try {
      const r = await api('/api/people', {method: 'POST', body: JSON.stringify({email: $('#p-email').value.trim()})});
      toast(r.invited ? 'Invited' : 'Added');
      viewPeople();
    } catch (err) { toast({exists: 'Already on the list', email: 'Check the email'}[err.message] || err.message); }
  });
}
document.addEventListener('click', async e => {
  const t = e.target.closest('[data-unperson]');
  if (!t) return;
  if (t.dataset.armed) {
    try { await api(`/api/people/${encodeURIComponent(t.dataset.unperson)}`, {method: 'DELETE'}); toast('Removed'); }
    catch (err) { toast(err.message); }
    viewPeople();
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
  const t = e.target.closest('[data-open],[data-refresh],[data-edit],[data-del],[data-retry]');
  if (!t || !$('.lib')) return;
  if (t.dataset.open) { openSource = openSource === +t.dataset.open ? null : +t.dataset.open; viewLibrary(); }
  else if (t.dataset.refresh) { await api(`/api/sources/${t.dataset.refresh}/refresh`, {method: 'POST'}); toast('Queued'); viewLibrary(); }
  else if (t.dataset.edit) { editing = +t.dataset.edit; await viewLibrary(); $('#addf').scrollIntoView({behavior: 'smooth'}); }
  else if (t.dataset.del) {
    if (t.dataset.armed) { await api(`/api/sources/${t.dataset.del}`, {method: 'DELETE'}); toast('Deleted'); viewLibrary(); }
    else { t.dataset.armed = '1'; t.textContent = 'Delete?'; t.classList.add('pill', 'bad'); setTimeout(() => { if (t.isConnected) { delete t.dataset.armed; t.textContent = '✕'; t.classList.remove('pill', 'bad'); } }, 4000); }
  }
  else if (t.dataset.retry) { await api(`/api/videos/${t.dataset.retry}/retry`, {method: 'POST'}); toast('Queued'); loadVideos(openSource); }
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
    else await viewSearch(params);
  } catch (err) { $('#main').innerHTML = `<div class="empty">${esc(err.message)}</div>`; }
  window.scrollTo(0, 0);
}
document.addEventListener('keydown', e => { if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); go('/search'); setTimeout(() => $('#q')?.focus(), 50); } });
window.addEventListener('hashchange', route);
$('#signout').addEventListener('click', async () => { await fetch('/api/auth/logout', {method: 'POST'}); location.href = '/login'; });
Promise.all([api('/api/config').then(c => { CFG = c; }), api('/api/me').then(m => { ME = m; })]).catch(() => {}).finally(() => {
  if (ME.username) { $('#me').textContent = ME.username; $('#me').hidden = false; $('#signout').hidden = false; }
  route(); pollWorker(); setInterval(pollWorker, 5000);
});
})();
