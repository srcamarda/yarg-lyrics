"""Interface web local do yarg-lyrics.

Uso:  .venv-rocm\\Scripts\\python.exe ui\\server.py   (abre http://127.0.0.1:8765)
Roda tudo no próprio PC: o pipeline (GPU) fica carregado no processo e as músicas são
processadas uma de cada vez numa fila em segundo plano.
"""
import os, sys, json, glob, threading, subprocess, re, webbrowser, traceback
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

import run as pipeline
from yl import charts, batch, align

STATE_PATH = os.path.join(ROOT, 'ui_state.json')
STATIC = os.path.join(ROOT, 'ui', 'static')
app = FastAPI(title='yarg-lyrics')


@app.on_event('startup')
async def _quiet_connection_resets():
    """No Windows, o asyncio registra como erro quando o navegador aborta um download de áudio
    (ao pular na música ou trocar Música/Só voz). É inofensivo: ignora só esse caso."""
    import asyncio
    loop = asyncio.get_running_loop()
    def handler(lp, ctx):
        if isinstance(ctx.get('exception'), (ConnectionResetError, ConnectionAbortedError)):
            return
        lp.default_exception_handler(ctx)
    loop.set_exception_handler(handler)
lock = threading.RLock()

# ------------------------------------------------------------------ estado persistente
def _key(folder):
    return os.path.normcase(os.path.abspath(folder))

def load_state():
    st = {}
    # semeia com relatórios da linha de comando (não-eval); o mais recente vence
    for p in sorted(glob.glob(os.path.join(ROOT, 'reports', '*.jsonl'))):
        if p.endswith('-eval.jsonl'):
            continue
        for line in open(p, encoding='utf-8'):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get('folder') and not str(r.get('status', '')).startswith('skip'):
                st.setdefault(_key(r['folder']), {})['report'] = r
    if os.path.exists(STATE_PATH):
        for k, v in json.load(open(STATE_PATH, encoding='utf-8')).items():
            st.setdefault(k, {}).update(v)
    return st

STATE = load_state()

def save_state():
    with lock:
        tmp = STATE_PATH + '.tmp'
        json.dump(STATE, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False)
        os.replace(tmp, STATE_PATH)

# ------------------------------------------------------------------ listagem
REPORT_KEYS = ('status', 'lyrics_source', 'lrclib', 'lrc_offset_s', 'lines_realigned', 'phrases', 'words',
               'quality', 'vocals', 'seconds', 'mode', 'lang')

def song_info(folder):
    files = {f.lower(): f for f in os.listdir(folder)}
    ini = charts.read_ini(folder)
    info = {'folder': folder, 'name': os.path.basename(folder),
            'artist': ini.get('artist', ''), 'title': ini.get('name', '') or os.path.basename(folder),
            'format': 'chart' if ('notes.chart' in files or 'notes.chart.bak' in files) else 'mid',
            'applied': any(f'notes.{e}.bak' in files for e in ('chart', 'mid')),
            'generated': bool(batch.generated(folder)),
            'nolyrics': '.nolyrics' in files,
            'manual_lyrics': 'lyrics.txt' in files}
    try:
        info['has_lyrics'] = charts.open_chart(folder).has_lyrics()     # original (ou .bak)
    except Exception as e:
        info['has_lyrics'] = False
        info['read_error'] = f'{type(e).__name__}: {e}'
    s = STATE.get(_key(folder), {})
    rep = s.get('report') or {}
    info['report'] = {k: rep.get(k) for k in REPORT_KEYS}
    info['approved'] = s.get('approved', False)
    info['edited'] = s.get('edited', False)
    info['state'] = derive_state(info)
    return info

def derive_state(i):
    st = str((i.get('report') or {}).get('status') or '')
    if i['nolyrics']:
        return 'ignorada'
    if i['applied']:
        return 'aplicada'
    if i['has_lyrics']:
        return 'tem letra'
    if not st:
        return 'pendente'
    if st == 'ok' or (st == 'REVISAR' and i['approved']):
        return 'ok' if i['generated'] else 'pendente'
    if st == 'REVISAR':
        return 'revisar' if i['generated'] else 'pendente'
    if st.startswith('instrumental'):
        return 'instrumental'
    if st.startswith('sem letra'):
        return 'sem letra'
    if st.startswith('erro'):
        return 'erro'
    return 'pendente'

@app.get('/api/songs')
def songs(root: str):
    if not os.path.isdir(root):
        raise HTTPException(404, 'Pasta não encontrada')
    out = []
    for f in sorted(batch.find_songs(root), key=lambda x: os.path.basename(x).lower()):
        try:
            out.append(song_info(f))
        except Exception as e:
            out.append({'folder': f, 'name': os.path.basename(f), 'title': os.path.basename(f), 'artist': '',
                        'state': 'erro', 'read_error': str(e), 'report': {}})
    return {'root': root, 'songs': out}

@app.get('/api/song')
def song(folder: str):
    return song_info(folder)

@app.post('/api/pick-folder')
def pick_folder(initial: str = Body('', embed=True)):
    """Abre o seletor de pasta nativo do Windows (tkinter) no próprio PC."""
    res = {}
    def ask():
        import tkinter as tk
        from tkinter import filedialog
        r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)
        res['path'] = filedialog.askdirectory(initialdir=initial or None, title='Escolha a pasta de músicas')
        r.destroy()
    t = threading.Thread(target=ask); t.start(); t.join()
    return {'path': os.path.normpath(res['path']) if res.get('path') else ''}

# ------------------------------------------------------------------ fila de execução
JOB = {'running': False, 'done': 0, 'total': 0, 'current': None, 'cancel': False, 'log': []}

def worker(items, force):
    try:
        for f in items:
            if JOB['cancel']:
                break
            JOB['current'] = os.path.basename(f)
            try:
                r = pipeline.process(f, False, force)
            except Exception as e:
                traceback.print_exc()
                r = {'folder': f, 'status': f'erro: {type(e).__name__}: {e}'}
            r['folder'] = f
            with lock:
                s = STATE.setdefault(_key(f), {})
                if not str(r.get('status', '')).startswith('skip'):
                    s['report'] = r
                    s['approved'] = False
                    s['edited'] = False
            save_state()
            JOB['done'] += 1
            JOB['log'].append({'folder': f, 'name': os.path.basename(f), 'status': r.get('status')})
    finally:
        JOB.update(running=False, current=None, cancel=False)

@app.post('/api/run')
def run_songs(folders: list = Body(..., embed=True), force: bool = Body(True, embed=True)):
    if JOB['running']:
        raise HTTPException(409, 'Já existe uma execução em andamento')
    JOB.update(running=True, done=0, total=len(folders), current=None, cancel=False, log=[])
    threading.Thread(target=worker, args=(list(folders), force), daemon=True).start()
    return {'started': len(folders)}

@app.post('/api/cancel')
def cancel():
    JOB['cancel'] = True
    return {'ok': True}

@app.get('/api/job')
def job():
    return {k: JOB[k] for k in ('running', 'done', 'total', 'current')} | {'log': JOB['log'][-200:]}

# ------------------------------------------------------------------ ações
@app.post('/api/apply')
def apply(folders: list = Body(..., embed=True)):
    n = 0
    for f in folders:
        if song_info(f)['state'] == 'ok' and batch.apply(f):
            n += 1
    return {'applied': n}

@app.post('/api/restore')
def restore(folders: list = Body(..., embed=True)):
    return {'restored': sum(batch.restore(f) for f in folders)}

@app.post('/api/approve')
def approve(folder: str = Body(..., embed=True), value: bool = Body(True, embed=True)):
    with lock:
        STATE.setdefault(_key(folder), {})['approved'] = value
    save_state()
    return song_info(folder)

@app.post('/api/nolyrics')
def nolyrics(folder: str = Body(..., embed=True), value: bool = Body(True, embed=True)):
    p = os.path.join(folder, '.nolyrics')
    if value:
        open(p, 'w', encoding='ascii').write('marcada na interface do yarg-lyrics: nao gerar letra\n')
    elif os.path.exists(p):
        os.remove(p)
    return song_info(folder)

# ------------------------------------------------------------------ letra manual
@app.get('/api/lyrics-text')
def get_lyrics_text(folder: str):
    """Texto para edição: lyrics.txt se existir; senão o LRC do LRCLIB usado na última execução."""
    p = os.path.join(folder, 'lyrics.txt')
    if os.path.exists(p):
        return {'source': 'manual', 'text': lyrics.read_text(p)}
    lp = os.path.join(pipeline.cache_dir(folder), 'lrclib.json')
    if os.path.exists(lp):
        rec = json.load(open(lp, encoding='utf-8')) or {}
        txt = rec.get('syncedLyrics') or rec.get('plainLyrics') or ''
        if txt:
            return {'source': 'lrclib', 'text': txt}
    return {'source': 'vazio', 'text': ''}

@app.post('/api/lyrics-text')
def save_lyrics_text(folder: str = Body(..., embed=True), text: str = Body(..., embed=True)):
    p = os.path.join(folder, 'lyrics.txt')
    if text.strip():
        open(p, 'w', encoding='utf-8').write(text.strip() + '\n')
    elif os.path.exists(p):
        os.remove(p)
    return {'saved': bool(text.strip())}

# ------------------------------------------------------------------ revisão: letra + áudio
def _lyric_file(folder):
    g = batch.generated(folder)
    if g:
        return g
    files = {f.lower(): f for f in os.listdir(folder)}
    for n in ('notes.chart', 'notes.mid'):
        if n in files:
            return os.path.join(folder, files[n])
    return None

def info_applied(folder):
    files = {f.lower() for f in os.listdir(folder)}
    return any(f'notes.{e}.bak' in files for e in ('chart', 'mid'))

def _clean(s):
    return re.sub(r'[#^*%$/§]', '', s).replace('_', ' ')

def get_phrases(folder):
    """Frases/palavras da letra atual da música (gerada, aplicada ou oficial), em tempo de ÁUDIO."""
    path = _lyric_file(folder)
    if not path:
        return None, []
    ch = charts.Chart(path) if path.lower().endswith('.chart') else charts.Midi(path)
    lyr, phr = ch.read_lyrics()
    delay = charts.audio_delay(folder, charts.open_chart(folder))
    tt = ch.tmap.t2s
    words = [{'t': round(tt(t) + delay, 3), 'text': _clean(x)} for t, x in lyr if x.strip() not in ('+', '')]
    phrases = []
    for a, b in phr:
        sa, sb = tt(a) + delay, tt(b) + delay
        ws = [w for w in words if sa - 1e-3 <= w['t'] <= sb + 1e-3]
        if ws:
            phrases.append({'start': round(sa, 3), 'end': round(sb, 3), 'words': ws})
    if not phrases and words:           # sem marcadores de frase: agrupa por pausas
        cur = [words[0]]
        for w in words[1:]:
            if w['t'] - cur[-1]['t'] > 1.5 or len(cur) >= 10:
                phrases.append({'start': cur[0]['t'], 'end': cur[-1]['t'] + 0.5, 'words': cur}); cur = []
            cur.append(w)
        phrases.append({'start': cur[0]['t'], 'end': cur[-1]['t'] + 0.5, 'words': cur})
    return path, phrases

@app.get('/api/review')
def review(folder: str):
    path, phrases = get_phrases(folder)
    if not path:
        raise HTTPException(404, 'Nenhuma letra para revisar')
    delay = charts.audio_delay(folder, charts.open_chart(folder))
    cd = pipeline.cache_dir(folder)
    ap = os.path.join(cd, 'aligned.json')
    if os.path.exists(ap) and (batch.generated(folder) or info_applied(folder)):
        try:
            al = json.load(open(ap, encoding='utf-8'))
            starts = [(p['words'][0]['t'] + delay, p.get('flag', 0)) for p in al if p.get('words')]
            for ph in phrases:
                t0 = ph['words'][0]['t']
                best = min(starts, key=lambda s: abs(s[0] - t0), default=None)
                ph['flag'] = best[1] if best and abs(best[0] - t0) < 0.3 else 0
        except (ValueError, KeyError):
            pass
    has_voc = any(os.path.exists(os.path.join(cd, n)) for n in ('vocals16k.wav', 'vocals16k_mix.wav'))
    return {'source': os.path.basename(path), 'phrases': phrases, 'has_vocals': has_voc, 'info': song_info(folder)}

def write_phrases(folder, phrases, keep_flags=True):
    """Grava frases (tempo de áudio) no chart gerado; se já aplicada, no próprio chart (original fica no .bak)."""
    gen = batch.generated(folder)
    base = charts.open_chart(folder)                 # original (ou o .bak, se já aplicada)
    delay = charts.audio_delay(folder, base)
    out = []
    for ph in phrases:
        ws = [{'t': float(w['t']) - delay, 'text': w['text']} for w in ph['words'] if str(w.get('text', '')).strip()]
        if ws:
            out.append({'start': float(ph.get('start', ws[0]['t'] + delay)) - delay,
                        'end': float(ph.get('end', ws[-1]['t'] + delay + 0.5)) - delay, 'words': ws})
    out.sort(key=lambda p: p['words'][0]['t'])
    align.fix_bounds(out, gap=0.02)
    if gen:
        target = gen
    else:
        files = {f.lower(): f for f in os.listdir(folder)}
        name = 'notes.chart' if base.kind == 'chart' else 'notes.mid'
        target = os.path.join(folder, files.get(name, name))
        if not os.path.exists(target + '.bak'):
            import shutil
            shutil.copy2(target, target + '.bak')
    base.write_lyrics(out, target)
    ap = os.path.join(pipeline.cache_dir(folder), 'aligned.json')
    if keep_flags:
        try:
            old = json.load(open(ap, encoding='utf-8')) if os.path.exists(ap) else []
            if len(old) == len(out):
                for a, b in zip(out, old):
                    a['flag'] = b.get('flag', 0)
        except ValueError:
            pass
    json.dump(out, open(ap, 'w', encoding='utf-8'), ensure_ascii=False)
    return target, len(out)

@app.post('/api/adjust')
def adjust(folder: str = Body(..., embed=True), phrases: list = Body(..., embed=True)):
    """Salva ajustes manuais de tempo (frases/palavras em tempo de áudio) no chart gerado ou aplicado."""
    if song_info(folder)['state'] == 'tem letra':
        raise HTTPException(400, 'Esta música já vinha com letra oficial; ajustes só valem para letras geradas aqui')
    target, n = write_phrases(folder, phrases)
    with lock:
        STATE.setdefault(_key(folder), {})['edited'] = True
    save_state()
    return {'saved': os.path.basename(target), 'phrases': n}

# ------------------------------------------------------------------ outras versões da mesma música
from yl import twins as twinlib
LIB_INDEX = {}

def library_index(lib):
    """{chave normalizada artista/título: [pastas]} da biblioteca inteira (cache em memória, 10 min)."""
    import time
    ent = LIB_INDEX.get(lib)
    if ent and time.time() - ent[0] < 600:
        return ent[1]
    idx = {}
    for f in batch.find_songs(lib):
        try:
            idx.setdefault(twinlib.key(f), []).append(f)
        except Exception:
            pass
    LIB_INDEX[lib] = (time.time(), idx)
    return idx

def _lyr_kind(folder):
    i = song_info(folder)
    if i['state'] == 'tem letra':
        return 'oficial'
    if i['generated'] or i['applied']:
        return 'gerada'
    return 'sem'

def _compare(a, b):
    fa = twinlib.fingerprint(a, pipeline.cache_dir(a))
    fb = twinlib.fingerprint(b, pipeline.cache_dir(b))
    if fa is None or fb is None:
        return None
    c = twinlib.compare(fa, fb)
    c['verdict'] = twinlib.verdict(c)
    return c

@app.get('/api/twins')
def find_twins(folder: str, lib: str):
    idx = library_index(lib)
    k = twinlib.key(folder)
    me = _key(folder)
    out = []
    for f in idx.get(k, []):
        if _key(f) == me:
            continue
        c = _compare(folder, f)
        out.append({'folder': f, 'setlist': os.path.basename(os.path.dirname(f)), 'name': os.path.basename(f),
                    'lyrics': _lyr_kind(f), 'cmp': c})
    return {'mine': _lyr_kind(folder), 'twins': out}

@app.post('/api/copy-lyrics')
def copy_lyrics(source: str = Body(..., embed=True), target: str = Body(..., embed=True)):
    """Copia a letra de uma versão para outra com o MESMO áudio, deslocando pela defasagem medida."""
    if _lyr_kind(target) == 'oficial':
        raise HTTPException(400, 'A música de destino já tem letra oficial')
    c = _compare(source, target)
    if not c or c['verdict'] != 'igual':
        raise HTTPException(400, 'O áudio das duas versões não é o mesmo; a letra não encaixaria')
    path, phrases = get_phrases(source)
    if not phrases:
        raise HTTPException(400, 'A versão de origem não tem letra')
    off = c['offset_s']                      # t_destino = t_origem + offset
    moved = [{'start': p['start'] + off, 'end': p['end'] + off,
              'words': [{'t': w['t'] + off, 'text': w['text']} for w in p['words']]} for p in phrases]
    moved = [p for p in moved if p['words'][0]['t'] >= 0]
    tpath, n = write_phrases(target, moved, keep_flags=False)
    rep = {'folder': target, 'status': 'ok', 'lyrics_source': 'cópia', 'copied_from': source,
           'twin': c, 'phrases': n, 'words': sum(len(p['words']) for p in moved)}
    with lock:
        s = STATE.setdefault(_key(target), {})
        s['report'] = rep
        s['approved'] = False
        s['edited'] = False
    save_state()
    return {'saved': os.path.basename(tpath), 'phrases': n, 'offset_s': off}

def _preview_mix(folder):
    """Mix de todos os stems num .ogg em cache (para tocar no navegador)."""
    cd = pipeline.cache_dir(folder)
    out = os.path.join(cd, 'preview_mix.ogg')
    st = align.stems(folder)
    if not st:
        raise HTTPException(404, 'Sem áudio na pasta')
    newest = max(os.path.getmtime(p) for p in st)
    if os.path.exists(out) and os.path.getmtime(out) >= newest:
        return out
    cmd = ['ffmpeg', '-v', 'error', '-y']
    for p in st:
        cmd += ['-i', p]
    if len(st) > 1:
        cmd += ['-filter_complex', f'amix=inputs={len(st)}:normalize=0:duration=longest,alimiter=limit=0.95']
    cmd += ['-c:a', 'libvorbis', '-q:a', '4', out]
    subprocess.run(cmd, check=True)
    return out

@app.get('/api/audio')
def audio(folder: str, kind: str = 'mix'):
    if kind == 'vocals':
        cd = pipeline.cache_dir(folder)
        for n in ('vocals16k.wav', 'vocals16k_mix.wav'):
            p = os.path.join(cd, n)
            if os.path.exists(p):
                return FileResponse(p, media_type='audio/wav')
        raise HTTPException(404, 'A voz separada ainda não existe: gere a letra desta música primeiro')
    return FileResponse(_preview_mix(folder), media_type='audio/ogg')

# ------------------------------------------------------------------ estáticos
app.mount('/', StaticFiles(directory=STATIC, html=True), name='static')

if __name__ == '__main__':
    port = int(os.environ.get('YL_PORT', 8765))
    if '--no-browser' not in sys.argv:
        threading.Timer(1.5, lambda: webbrowser.open(f'http://127.0.0.1:{port}')).start()
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')
