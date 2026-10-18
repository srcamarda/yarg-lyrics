'use strict';
const $ = (id) => document.getElementById(id);
const api = async (path, body) => {
  const opt = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (e) { /* sem corpo */ }
    throw new Error(msg);
  }
  return r.json();
};
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* sem storage */ } },
};

// ------------------------------------------------------------------ estado
const S = { root: '', songs: [], filter: 'todas', q: '', sort: ['state', 1], sel: new Set(), active: null, job: null, logSeen: 0 };
const STATES = ['revisar', 'ok', 'pendente', 'sem letra', 'instrumental', 'erro', 'aplicada', 'tem letra', 'ignorada'];
const LABEL = { 'revisar': 'Revisar', 'ok': 'Ok', 'pendente': 'Pendente', 'sem letra': 'Sem letra', 'instrumental': 'Instrumental',
  'erro': 'Erro', 'aplicada': 'Aplicada', 'tem letra': 'Já tem letra', 'ignorada': 'Sem letra (marcada)' };
const cls = (st) => 's-' + st.replace(/\s+/g, '-');

const metric = (s) => {
  const r = s.report || {}, q = r.quality || {};
  return { conf: q.mean_score, dis: q.lrc_disagree_frac, dd: (r.lrclib || {}).duration_delta_s, voice: q.chars_per_s };
};
// espelha yl/align.py:verdict para explicar o porquê do "Revisar"
function reasons(s) {
  const m = metric(s), out = [];
  if (m.dis > 0.40) out.push(`${Math.round(m.dis * 100)}% das linhas fora do tempo do LRCLIB (versão diferente?)`);
  if (m.conf < 0.085) out.push(`confiança baixa (${m.conf.toFixed(2)})`);
  if (m.dd > 8 && (m.dis > 0.25 || m.conf < 0.12)) out.push(`versão do LRCLIB com ${m.dd.toFixed(0)} s de diferença de duração`);
  return out;
}
const fmt = (v, d = 2) => (v === undefined || v === null) ? '' : Number(v).toFixed(d);
const pct = (v) => (v === undefined || v === null) ? '' : Math.round(v * 100) + '%';
const mmss = (t) => { t = Math.max(0, t || 0); return Math.floor(t / 60) + ':' + String(Math.floor(t % 60)).padStart(2, '0'); };

function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.remove('show'), 3500);
}

// ------------------------------------------------------------------ pasta
async function load(root) {
  root = (root || '').trim();
  if (!root) return;
  $('load').disabled = true; $('load').textContent = 'Carregando…';
  try {
    const d = await api('/api/songs?root=' + encodeURIComponent(root));
    S.root = d.root; S.songs = d.songs; S.sel.clear();
    store.set('yl.root', root);
    $('bar').hidden = false; $('empty').hidden = d.songs.length > 0; $('table').hidden = d.songs.length === 0;
    if (!d.songs.length) $('empty').innerHTML = '<p>Nenhuma música encontrada nesta pasta.</p><p class="muted">É preciso uma pasta com <code>song.ini</code> e <code>notes.chart</code> ou <code>notes.mid</code>.</p>';
    render();
  } catch (e) { toast('Não deu para abrir a pasta: ' + e.message); }
  $('load').disabled = false; $('load').textContent = 'Carregar';
}
$('folderForm').addEventListener('submit', (e) => { e.preventDefault(); load($('root').value); });
$('pick').addEventListener('click', async () => {
  const d = await api('/api/pick-folder', { initial: $('root').value });
  if (d.path) { $('root').value = d.path; load(d.path); }
});

// ------------------------------------------------------------------ tabela
function visible() {
  const q = S.q.toLowerCase();
  let list = S.songs.filter((s) => (S.filter === 'todas' || s.state === S.filter) &&
    (!q || (s.artist + ' ' + s.title + ' ' + s.name).toLowerCase().includes(q)));
  const [k, dir] = S.sort;
  const key = (s) => {
    if (k === 'state') return STATES.indexOf(s.state);
    if (k === 'source') return (s.report || {}).lyrics_source || '';
    if (['conf', 'dis', 'dd', 'voice'].includes(k)) { const v = metric(s)[k]; return v === undefined || v === null ? -1 : v; }
    return (s[k] || '').toString().toLowerCase();
  };
  return list.sort((a, b) => { const x = key(a), y = key(b); return (x < y ? -1 : x > y ? 1 : 0) * dir || a.name.localeCompare(b.name); });
}

function renderChips() {
  const counts = { todas: S.songs.length };
  S.songs.forEach((s) => { counts[s.state] = (counts[s.state] || 0) + 1; });
  const order = ['todas', ...STATES].filter((k) => counts[k]);
  $('chips').innerHTML = order.map((k) =>
    `<button role="tab" data-f="${k}" aria-selected="${S.filter === k}">${k === 'todas' ? 'Todas' : LABEL[k]}<b>${counts[k]}</b></button>`).join('');
}

function render() {
  renderChips();
  const rows = visible();
  $('rows').innerHTML = rows.map((s) => {
    const m = metric(s), r = s.report || {};
    const src = s.state === 'tem letra' ? 'original' : r.lyrics_source === 'local' ? 'manual' : r.lyrics_source ? 'LRCLIB' : '';
    const warn = (v, bad) => (v !== undefined && v !== null && bad(v)) ? ' warn' : '';
    return `<tr data-f="${encodeURIComponent(s.folder)}" class="${S.active === s.folder ? 'active' : ''}">
      <td class="ck"><input type="checkbox" ${S.sel.has(s.folder) ? 'checked' : ''} aria-label="Selecionar"></td>
      <td><span class="chip ${cls(s.state)}">${LABEL[s.state] || s.state}${s.approved && s.state === 'ok' ? ' ✓' : ''}</span></td>
      <td title="${esc(s.artist)}">${esc(s.artist)}</td>
      <td title="${esc(s.title)}">${esc(s.title)}</td>
      <td class="num">.${s.format}</td>
      <td>${src}${s.manual_lyrics ? ' ✎' : ''}</td>
      <td class="num${warn(m.conf, (v) => v < 0.085)}">${fmt(m.conf)}</td>
      <td class="num${warn(m.dis, (v) => v > 0.4)}">${pct(m.dis)}</td>
      <td class="num${warn(m.dd, (v) => v > 8)}">${m.dd === undefined || m.dd === null ? '' : fmt(m.dd, 1) + ' s'}</td>
      <td class="num">${fmt(m.voice, 1)}</td></tr>`;
  }).join('');
  document.querySelectorAll('thead th').forEach((th) => th.classList.toggle('sorted', th.dataset.sort === S.sort[0]));
  $('ckAll').checked = rows.length > 0 && rows.every((s) => S.sel.has(s.folder));
  updateActions();
}
const esc = (s) => String(s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function selected() { return S.songs.filter((s) => S.sel.has(s.folder)); }
function updateActions() {
  const sel = selected(), running = S.job && S.job.running;
  const runnable = sel.filter((s) => !['tem letra', 'ignorada'].includes(s.state));
  const okN = sel.filter((s) => s.state === 'ok').length, apN = sel.filter((s) => s.state === 'aplicada').length;
  $('selCount').textContent = `${sel.length} selecionada${sel.length === 1 ? '' : 's'}`;
  $('runSel').disabled = running || !runnable.length;
  $('runSel').textContent = runnable.length ? `Gerar letras (${runnable.length})` : 'Gerar letras';
  $('applySel').disabled = running || !okN;
  $('applySel').textContent = okN ? `Aplicar ${okN} ok` : 'Aplicar';
  $('restoreSel').disabled = running || !apN;
  $('restoreSel').textContent = apN ? `Restaurar originais (${apN})` : 'Restaurar originais';
}

$('chips').addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) { S.filter = b.dataset.f; render(); } });
$('search').addEventListener('input', (e) => { S.q = e.target.value; render(); });
document.querySelector('thead').addEventListener('click', (e) => {
  const th = e.target.closest('th[data-sort]'); if (!th) return;
  S.sort = [th.dataset.sort, S.sort[0] === th.dataset.sort ? -S.sort[1] : 1]; render();
});
$('ckAll').addEventListener('change', (e) => { visible().forEach((s) => e.target.checked ? S.sel.add(s.folder) : S.sel.delete(s.folder)); render(); });
$('selVisible').addEventListener('click', () => { visible().forEach((s) => S.sel.add(s.folder)); render(); });
$('selNone').addEventListener('click', () => { S.sel.clear(); render(); });
$('rows').addEventListener('click', (e) => {
  const tr = e.target.closest('tr'); if (!tr) return;
  const f = decodeURIComponent(tr.dataset.f);
  if (e.target.type === 'checkbox') { e.target.checked ? S.sel.add(f) : S.sel.delete(f); updateActions(); $('ckAll').checked = visible().every((s) => S.sel.has(s.folder)); return; }
  openReview(f);
});

// ------------------------------------------------------------------ execução
async function runFolders(folders) {
  if (!folders.length) return;
  try { await api('/api/run', { folders, force: true }); S.logSeen = 0; toast(`Gerando letra de ${folders.length} música${folders.length > 1 ? 's' : ''}…`); poll(); }
  catch (e) { toast(e.message); }
}
$('runSel').addEventListener('click', () => runFolders(selected().filter((s) => !['tem letra', 'ignorada'].includes(s.state)).map((s) => s.folder)));
$('applySel').addEventListener('click', async () => {
  const f = selected().filter((s) => s.state === 'ok').map((s) => s.folder);
  if (!confirm(`Aplicar a letra em ${f.length} chart(s)? O original de cada um fica guardado como notes.*.bak.`)) return;
  const d = await api('/api/apply', { folders: f }); toast(`Letra aplicada em ${d.applied} chart(s)`); refresh(f);
});
$('restoreSel').addEventListener('click', async () => {
  const f = selected().filter((s) => s.state === 'aplicada').map((s) => s.folder);
  const d = await api('/api/restore', { folders: f }); toast(`${d.restored} original(is) restaurado(s)`); refresh(f);
});
$('cancel').addEventListener('click', async () => { await api('/api/cancel', {}); toast('A execução para depois da música atual'); });

async function poll() {
  const j = await api('/api/job'); S.job = j;
  $('job').hidden = !j.running && !j.total;
  $('jobCount').textContent = j.running ? `${j.done} de ${j.total}` : `Concluído: ${j.done} de ${j.total}`;
  $('jobCur').textContent = j.current ? '· ' + j.current : '';
  $('jobFill').style.width = j.total ? (100 * j.done / j.total) + '%' : '0';
  $('cancel').hidden = !j.running;
  const fresh = j.log.slice(S.logSeen); S.logSeen = j.log.length;
  if (fresh.length) await refresh(fresh.map((l) => l.folder));
  updateActions();
  if (j.running) setTimeout(poll, 1200);
  else if (j.total) { toast('Execução concluída'); setTimeout(() => { $('job').hidden = true; }, 6000); }
}

async function refresh(folders) {
  for (const f of folders) {
    try {
      const s = await api('/api/song?folder=' + encodeURIComponent(f));
      const i = S.songs.findIndex((x) => x.folder === f);
      if (i >= 0) S.songs[i] = s;
      if (S.active === f) await openReview(f, true);
    } catch (e) { /* pasta sumiu */ }
  }
  render();
}

// ------------------------------------------------------------------ revisão
const A = $('audio');
const R = { data: null, cur: -2, kind: 'mix', raf: 0, sel: null, step: 50, undo: [], dirty: false };

async function openReview(folder, keepAudio) {
  if (R.dirty && folder !== S.active && !confirm('Há ajustes de tempo não salvos nesta música. Descartar?')) return;
  if (folder !== S.active || !keepAudio) { R.sel = null; R.undo = []; setDirty(false); }
  S.active = folder; render();
  const s = S.songs.find((x) => x.folder === folder);
  $('review').hidden = false;
  $('rTitle').textContent = s.title; $('rArtist').textContent = s.artist;
  $('rChip').className = 'chip ' + cls(s.state); $('rChip').textContent = LABEL[s.state] || s.state;
  $('rWhy').textContent = s.state === 'revisar' ? reasons(s).join(' · ') : s.state === 'erro' ? (s.report.status || s.read_error || '') : '';
  renderStats(s); renderActions(s);
  R.data = null; R.cur = -2; drawLines(); $('phrMarks').innerHTML = '';
  try {
    R.data = await api('/api/review?folder=' + encodeURIComponent(folder));
    $('stageMsg').textContent = R.data.phrases.length ? '' : 'Este chart não tem letra.';
  } catch (e) {
    $('stageMsg').textContent = ['sem letra', 'instrumental', 'pendente', 'ignorada'].includes(s.state)
      ? 'Ainda não há letra para revisar.' + (s.state === 'sem letra' ? ' Use “Adicionar letra” para colar a letra e sincronizar.' : '') : e.message;
  }
  document.querySelector('.seg[data-kind="vocals"]').disabled = !(R.data && R.data.has_vocals);
  if (!keepAudio || !A.src) setAudio(R.kind === 'vocals' && R.data && R.data.has_vocals ? 'vocals' : 'mix', 0);
  $('tune').hidden = !(R.data && R.data.phrases.length) || s.state === 'tem letra';
  drawMarks(); drawLines(); showSel();
}

function renderStats(s) {
  const r = s.report || {}, q = r.quality || {}, m = metric(s);
  const rows = [];
  if (r.lyrics_source) rows.push(['Letra de', r.lyrics_source === 'local' ? 'lyrics.txt (manual)' : r.lyrics_source === 'synced' ? 'LRCLIB (sincronizada)' : 'LRCLIB (sem tempos)']);
  if (r.lrclib) rows.push(['Versão LRCLIB', `id ${r.lrclib.id} · ${fmt(m.dd, 1)} s de diferença de duração`]);
  if (r.lrc_offset_s !== undefined && r.lrc_offset_s !== null) rows.push(['Defasagem corrigida', `${fmt(r.lrc_offset_s, 1)} s`]);
  if (r.words) rows.push(['Palavras / frases', `${r.words} / ${r.phrases}` + (r.lines_realigned ? ` · ${r.lines_realigned} linhas realinhadas` : '')]);
  if (q.mean_score !== undefined) rows.push(['Confiança', fmt(q.mean_score)]);
  if (q.lrc_disagree_frac !== undefined) rows.push(['Desencontro com o LRCLIB', pct(q.lrc_disagree_frac)]);
  if (q.chars_per_s !== undefined) rows.push(['Voz detectada', `${fmt(q.chars_per_s, 1)} caracteres/s · ${r.vocals === 'stem' ? 'stem de voz' : 'separada pelo Demucs'}`]);
  if (r.seconds) rows.push(['Tempo de processamento', `${fmt(r.seconds, 0)} s`]);
  $('rStats').innerHTML = rows.map(([a, b]) => `<dt>${a}</dt><dd>${esc(b)}</dd>`).join('');
}

function renderActions(s) {
  const st = s.state, show = (id, on) => { $(id).hidden = !on; };
  show('rApprove', st === 'revisar');
  show('rUnapprove', st === 'ok' && s.approved);
  show('rApply', st === 'ok');
  show('rRestore', st === 'aplicada');
  show('rEdit', !['tem letra', 'ignorada'].includes(st));
  $('rEdit').textContent = st === 'sem letra' || st === 'pendente' ? 'Adicionar letra' : 'Editar letra e ressincronizar';
  show('rRerun', !['tem letra', 'ignorada', 'aplicada'].includes(st));
  show('rNoLyr', st !== 'tem letra');
  $('rNoLyr').textContent = s.nolyrics ? 'Desmarcar “sem letra”' : 'Não tem letra';
}

function setAudio(kind, t) {
  R.kind = kind;
  document.querySelectorAll('.seg').forEach((b) => { const on = b.dataset.kind === kind; b.classList.toggle('on', on); b.setAttribute('aria-checked', on); });
  const playing = !A.paused;
  A.src = `/api/audio?folder=${encodeURIComponent(S.active)}&kind=${kind}`;
  A.addEventListener('loadedmetadata', () => { A.currentTime = t || 0; if (playing) A.play(); drawMarks(); }, { once: true });
}
document.querySelector('.src').addEventListener('click', (e) => {
  const b = e.target.closest('.seg'); if (b && !b.disabled && b.dataset.kind !== R.kind) setAudio(b.dataset.kind, A.currentTime);
});
$('play').addEventListener('click', () => (A.paused ? A.play() : A.pause()));
A.addEventListener('play', () => { $('play').textContent = '❚❚'; $('play').setAttribute('aria-label', 'Pausar'); tick(); });
A.addEventListener('pause', () => { $('play').textContent = '▶'; $('play').setAttribute('aria-label', 'Tocar'); });
A.addEventListener('error', () => { if (S.active) $('stageMsg').textContent = 'Não deu para carregar o áudio desta música.'; });
$('timeline').addEventListener('click', (e) => {
  const r = $('timeline').getBoundingClientRect();
  if (A.duration) { A.currentTime = (e.clientX - r.left) / r.width * A.duration; update(); }
});

function drawMarks() {
  const d = A.duration;
  if (!R.data || !d) { $('phrMarks').innerHTML = ''; return; }
  $('phrMarks').innerHTML = R.data.phrases.map((p) =>
    `<span style="left:${100 * p.start / d}%;width:${Math.max(0.3, 100 * (p.end - p.start) / d)}%"></span>`).join('');
}

function phraseAt(t) {
  const P = R.data ? R.data.phrases : [];
  let i = -1;
  for (let k = 0; k < P.length; k++) { if (P[k].start - 0.25 <= t) i = k; else break; }
  return i;
}
function lineHTML(p, idx) {
  if (!p) return '';
  const sl = R.sel && R.sel.i === idx;
  return `<span data-i="${idx}"${sl ? ' class="selline"' : ''}>` + p.words.map((w, j) =>
    `<span class="w${sl && R.sel.j === j ? ' picked' : ''}" data-j="${j}">${esc(w.text)}</span>`).join(' ') + '</span>';
}
function drawLines() {
  const P = R.data ? R.data.phrases : [], i = R.cur;
  $('lPrev').innerHTML = lineHTML(P[i - 1], i - 1);
  $('lCur').innerHTML = lineHTML(P[i], i);
  $('lNext').innerHTML = lineHTML(P[i + 1], i + 1);
}
function update() {
  const t = A.currentTime || 0;
  $('time').textContent = `${mmss(t)} / ${mmss(A.duration)}`;
  $('pos').style.left = A.duration ? (100 * t / A.duration) + '%' : 0;
  if (!R.data) return;
  const i = phraseAt(t);
  if (i !== R.cur) { R.cur = i; drawLines(); }
  const p = R.data.phrases[i];
  if (!p) return;
  const ws = $('lCur').querySelectorAll('.w');
  let last = -1;
  p.words.forEach((w, j) => { if (w.t <= t) last = j; });
  ws.forEach((el, j) => {
    el.classList.toggle('sung', j <= last);
    el.classList.toggle('now', j === last && t - p.words[j].t < 0.45);
  });
}
function tick() { update(); if (!A.paused) R.raf = requestAnimationFrame(tick); }
A.addEventListener('seeked', update);
$('stage').addEventListener('click', (e) => {
  const s = e.target.closest('[data-i]'); if (!s || !R.data) return;
  const i = +s.dataset.i, p = R.data.phrases[i]; if (!p) return;
  const w = e.target.closest('.w');
  // duplo clique detectado pelo tempo: o 1º clique redesenha as linhas, então o evento dblclick nativo se perde
  const now = performance.now(), dbl = R.lastClick && R.lastClick.i === i && now - R.lastClick.t < 450;
  R.lastClick = dbl ? null : { i, t: now };
  R.sel = { i, j: w ? +w.dataset.j : 0 };
  if (dbl) A.currentTime = Math.max(0, p.start - 0.2);
  R.cur = -2; update(); showSel();
});
function showSel() {
  const P = R.data ? R.data.phrases : [];
  $('selLine').textContent = R.sel && P[R.sel.i] ? `${R.sel.i + 1} de ${P.length}` : '— clique numa palavra';
  $('selWord').textContent = R.sel && P[R.sel.i] ? `${R.sel.j + 1} de ${P[R.sel.i].words.length}` : '—';
  document.querySelectorAll('[data-shift="line"],[data-shift="word"],[data-here],#replay').forEach((b) => { b.disabled = !R.sel; });
}

// ------------------------------------------------------------------ ajustes de tempo
function setDirty(on) {
  R.dirty = on;
  $('dirty').textContent = on ? 'Alterações não salvas' : 'Sem alterações';
  $('dirty').classList.toggle('on', on);
  $('saveAdj').disabled = !on; $('undo').disabled = !R.undo.length;
}
const snap = () => JSON.stringify(R.data.phrases);
function shift(kind, dir, secs) {
  if (!R.data || (kind !== 'all' && !R.sel)) return;
  const P = R.data.phrases, d = secs !== undefined ? secs : dir * R.step / 1000;
  const before = snap();
  const allWords = () => P.flatMap((p) => p.words);
  if (kind === 'all') {
    const first = P[0].words[0].t, delta = Math.max(d, -first + 0.05);
    P.forEach((p) => { p.start = Math.max(0, p.start + delta); p.end += delta; p.words.forEach((w) => { w.t += delta; }); });
  } else if (kind === 'line') {
    const i = R.sel.i, p = P[i];
    const lo = i > 0 ? P[i - 1].words[P[i - 1].words.length - 1].t + 0.03 : 0.05;
    const hi = i < P.length - 1 ? P[i + 1].words[0].t - 0.03 : Infinity;
    let delta = d;
    if (p.words[0].t + delta < lo) delta = lo - p.words[0].t;
    if (p.words[p.words.length - 1].t + delta > hi) delta = hi - p.words[p.words.length - 1].t;
    if (Math.abs(delta) < 1e-4) { toast('A linha já encostou na vizinha'); return; }
    if (secs !== undefined && Math.abs(delta - d) > 0.005) toast('A linha foi até onde a vizinha permite');
    p.words.forEach((w) => { w.t += delta; }); p.start = Math.max(0, p.start + delta); p.end += delta;
  } else {
    const ws = allWords(), p = P[R.sel.i], w = p.words[R.sel.j], k = ws.indexOf(w);
    const lo = k > 0 ? ws[k - 1].t + 0.03 : 0.05, hi = k < ws.length - 1 ? ws[k + 1].t - 0.03 : Infinity;
    const nt = Math.min(hi, Math.max(lo, w.t + d));
    if (Math.abs(nt - w.t) < 1e-4) { toast('A palavra já encostou na vizinha'); return; }
    if (secs !== undefined && Math.abs(nt - (w.t + d)) > 0.005) toast('A palavra foi até onde a vizinha permite — use “Linha aqui” para mover a linha toda');
    w.t = nt;
    p.start = Math.min(p.start, p.words[0].t - 0.01); p.end = Math.max(p.end, p.words[p.words.length - 1].t + 0.05);
  }
  // frases nunca se sobrepõem e sempre contêm as próprias palavras
  for (let i = 0; i < P.length - 1; i++) {
    const a = P[i], b = P[i + 1];
    if (a.end > b.start - 0.02) { a.end = Math.max(a.words[a.words.length - 1].t + 0.03, b.words[0].t - 0.02); b.start = Math.min(b.words[0].t - 0.01, a.end + 0.01); }
  }
  R.undo.push(before); if (R.undo.length > 200) R.undo.shift();
  setDirty(true); R.cur = -2; update(); drawMarks();
}
document.querySelector('.tune').addEventListener('click', (e) => {
  const b = e.target.closest('button'); if (!b) return;
  if (b.dataset.step) {
    R.step = +b.dataset.step;
    document.querySelectorAll('.steps .seg').forEach((x) => x.classList.toggle('on', x === b));
  } else if (b.dataset.shift) shift(b.dataset.shift, +b.dataset.dir);
});
function placeHere(kind) {
  if (!R.sel || !R.data) { toast('Selecione uma palavra primeiro'); return; }
  const w = R.data.phrases[R.sel.i].words[R.sel.j];
  shift(kind, 0, A.currentTime - w.t);
}
document.querySelectorAll('[data-here]').forEach((b) => b.addEventListener('click', () => placeHere(b.dataset.here)));
function replayLine() {
  if (!R.sel || !R.data) return;
  A.currentTime = Math.max(0, R.data.phrases[R.sel.i].start - 0.8); update(); A.play();
}
$('replay').addEventListener('click', replayLine);
$('undo').addEventListener('click', () => {
  if (!R.undo.length) return;
  R.data.phrases = JSON.parse(R.undo.pop()); setDirty(R.undo.length > 0); R.cur = -2; update(); drawMarks();
});
$('saveAdj').addEventListener('click', async () => {
  try {
    const d = await api('/api/adjust', { folder: S.active, phrases: R.data.phrases });
    R.undo = []; setDirty(false); toast(`Ajustes salvos em ${d.saved}`); refresh([S.active]);
  } catch (e) { toast('Não deu para salvar: ' + e.message); }
});
window.addEventListener('beforeunload', (e) => { if (R.dirty) { e.preventDefault(); e.returnValue = ''; } });

// painel redimensionável
(() => {
  const g = $('grip'), rv = $('review');
  const w0 = +store.get('yl.rw'); if (w0) rv.style.setProperty('--rw', w0 + 'px');
  g.addEventListener('pointerdown', (e) => {
    g.setPointerCapture(e.pointerId); g.classList.add('drag');
    const move = (ev) => { const w = Math.min(window.innerWidth * 0.72, Math.max(380, window.innerWidth - ev.clientX)); rv.style.setProperty('--rw', w + 'px'); };
    const up = () => { g.classList.remove('drag'); g.removeEventListener('pointermove', move); store.set('yl.rw', parseInt(rv.style.getPropertyValue('--rw'), 10)); };
    g.addEventListener('pointermove', move); g.addEventListener('pointerup', up, { once: true });
  });
})();
document.addEventListener('keydown', (e) => {
  if (!S.active || $('editor').open || /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
  if (e.code === 'Space') { e.preventDefault(); A.paused ? A.play() : A.pause(); }
  else if (e.code === 'ArrowLeft') { A.currentTime = Math.max(0, A.currentTime - 5); update(); }
  else if (e.code === 'ArrowRight') { A.currentTime = Math.min(A.duration || 0, A.currentTime + 5); update(); }
  else if (e.key === '[') shift('line', -1);
  else if (e.key === ']') shift('line', 1);
  else if (e.key === ',') shift('word', -1);
  else if (e.key === '.') shift('word', 1);
  else if (e.key === 'r' || e.key === 'R') replayLine();
  else if (e.key === 'Enter') { e.preventDefault(); placeHere(e.shiftKey ? 'line' : 'word'); }
  else if ((e.ctrlKey || e.metaKey) && e.key === 'z') { e.preventDefault(); $('undo').click(); }
});
$('rClose').addEventListener('click', () => { if (R.dirty && !confirm('Há ajustes de tempo não salvos. Descartar?')) return; setDirty(false); R.undo = []; A.pause(); $('review').hidden = true; S.active = null; render(); });

// ações da revisão
$('rApprove').addEventListener('click', async () => { await api('/api/approve', { folder: S.active, value: true }); toast('Marcada como ok'); refresh([S.active]); });
$('rUnapprove').addEventListener('click', async () => { await api('/api/approve', { folder: S.active, value: false }); refresh([S.active]); });
$('rApply').addEventListener('click', async () => { const d = await api('/api/apply', { folders: [S.active] }); toast(d.applied ? 'Letra aplicada no chart (original guardado como .bak)' : 'Nada para aplicar'); refresh([S.active]); });
$('rRestore').addEventListener('click', async () => { await api('/api/restore', { folders: [S.active] }); toast('Original restaurado'); refresh([S.active]); });
$('rRerun').addEventListener('click', () => runFolders([S.active]));
$('rNoLyr').addEventListener('click', async () => {
  const s = S.songs.find((x) => x.folder === S.active);
  await api('/api/nolyrics', { folder: S.active, value: !s.nolyrics }); refresh([S.active]);
});

// editor de letra
$('rEdit').addEventListener('click', async () => {
  const s = S.songs.find((x) => x.folder === S.active);
  const d = await api('/api/lyrics-text?folder=' + encodeURIComponent(S.active));
  $('edTitle').textContent = `Letra · ${s.artist} - ${s.title}`;
  $('edSrc').textContent = d.source === 'manual' ? 'Letra manual (lyrics.txt) desta pasta.'
    : d.source === 'lrclib' ? 'Texto que veio do LRCLIB. Corrija o que estiver errado — ao salvar, vira a letra manual desta música.'
    : 'Nenhuma letra encontrada. Cole a letra aqui.';
  $('edText').value = d.text; $('edClear').hidden = d.source !== 'manual';
  $('editor').showModal(); $('edText').focus();
});
$('edSave').addEventListener('click', async () => {
  const text = $('edText').value;
  if (!text.trim()) { toast('Cole a letra antes de salvar'); return; }
  await api('/api/lyrics-text', { folder: S.active, text }); $('editor').close();
  runFolders([S.active]);
});
$('edClear').addEventListener('click', async () => {
  await api('/api/lyrics-text', { folder: S.active, text: '' }); $('editor').close();
  toast('Letra manual removida. Use “Gerar de novo” para voltar à letra do LRCLIB.'); refresh([S.active]);
});

// ------------------------------------------------------------------ início
const last = store.get('yl.root');
if (last) { $('root').value = last; load(last); }
api('/api/job').then((j) => { if (j.running) poll(); });
