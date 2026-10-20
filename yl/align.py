"""Separação de voz (Demucs) + alinhamento forçado por palavra (MMS_FA, multilíngue)."""
import os, re, subprocess, sys, shutil, statistics, unicodedata
import numpy as np
import torch, torchaudio
import soundfile as sf

SR = 16000
DEVICE = os.environ.get('YL_DEVICE') or ('cuda' if torch.cuda.is_available() else 'cpu')
SKIP_STEMS = ('preview', 'crowd')
AUDIO_EXT = ('.ogg', '.opus', '.mp3', '.wav', '.flac')

def _ffmpeg_decode(paths, out_wav, sr, mono):
    cmd = ['ffmpeg', '-v', 'error', '-y']
    for p in paths:
        cmd += ['-i', p]
    if len(paths) > 1:
        cmd += ['-filter_complex', f'amix=inputs={len(paths)}:normalize=0:duration=longest']
    cmd += ['-ar', str(sr), '-ac', '1' if mono else '2', out_wav]
    subprocess.run(cmd, check=True)

def stems(folder):
    fs = [f for f in os.listdir(folder) if f.lower().endswith(AUDIO_EXT)]
    return [os.path.join(folder, f) for f in fs if not f.lower().startswith(SKIP_STEMS)]

def vocals_16k(folder, cache):
    """Gera cache/vocals16k.wav. Usa stem 'vocals' se existir; senão Demucs no mix completo."""
    ignore_stem = os.environ.get('YL_IGNORE_VOCAL_STEM') == '1'   # simula músicas sem stem de voz
    all_stems = stems(folder)
    big = max((os.path.getsize(p) for p in all_stems), default=0)
    # stems de voz minúsculos (ex.: vocals_2.ogg de 23 KB, quase silêncio) não contam como voz
    voc = [] if ignore_stem else [p for p in all_stems if os.path.basename(p).lower().startswith('vocals')
                                  and os.path.getsize(p) >= 0.2 * big]
    if voc:
        out = os.path.join(cache, 'vocals16k.wav')
        if not os.path.exists(out):
            _ffmpeg_decode(voc, out, SR, True)
            return out, 'stem'
        return out, 'cache'
    sep = separator()
    tag = '' if sep == 'htdemucs' else '_' + re.sub(r'\W+', '', os.path.splitext(sep)[0])[:24]
    out = os.path.join(cache, ('vocals16k_mix' if ignore_stem else 'vocals16k') + tag + '.wav')
    if os.path.exists(out):
        return out, 'cache'
    if sep == 'none':                       # sem separação: o mix inteiro vai p/ o alinhador (teste do ALT-DALI)
        _ffmpeg_decode(all_stems, out, SR, True)
        return out, 'mix'
    mix = os.path.join(cache, 'mix.wav')
    _ffmpeg_decode(all_stems, mix, 44100, False)
    try:
        if sep == 'htdemucs':
            subprocess.run([sys.executable, '-m', 'demucs', '--two-stems=vocals', '-n', 'htdemucs', '-d', DEVICE,
                            '-o', os.path.join(cache, 'demucs'), mix], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            dv = os.path.join(cache, 'demucs', 'htdemucs', 'mix', 'vocals.wav')
        else:
            free_gpu_cache()        # o separador roda em outro processo: não deixa a VRAM presa no cache deste
            dv = _uvr_vocals(sep, mix, os.path.join(cache, 'demucs'))
        _ffmpeg_decode([dv], out, SR, True)
    finally:
        os.remove(mix)
        shutil.rmtree(os.path.join(cache, 'demucs'), ignore_errors=True)
    return out, 'demucs' if sep == 'htdemucs' else 'roformer'

# ---------------------------------------------------------------- separador (htdemucs ou modelos UVR via audio-separator)
import importlib.util
# padrão: MelBand RoFormer (gabarito: linhas ruins 17,7% -> 12,1% contra o htdemucs); htdemucs se faltar o audio-separator
DEFAULT_SEPARATOR = 'vocals_mel_band_roformer.ckpt' if importlib.util.find_spec('audio_separator') else 'htdemucs'
MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cache', 'models')
_uvr = {}

def free_gpu_cache():
    """Devolve ao driver a VRAM que o PyTorch guarda em cache (ativações de músicas anteriores).
    Num processo longo (a interface) o cache chegava a 4+ GB e jogava o separador p/ a memória compartilhada (4x mais lento)."""
    if torch.cuda.is_available():
        import gc
        gc.collect()
        torch.cuda.empty_cache()

def unload_models():
    """Tira os modelos de alinhamento da GPU (antes de separar várias vozes num processo longo, como a interface)."""
    _models.clear()
    free_gpu_cache()

def separator():
    """YL_SEPARATOR=htdemucs (padrão) ou um arquivo de modelo do audio-separator (ex.: vocals_mel_band_roformer.ckpt)."""
    return os.environ.get('YL_SEPARATOR') or DEFAULT_SEPARATOR

def _uvr_vocals(model, mix, out_dir):
    """Separa num subprocesso novo: no ROCm/Windows o mesmo Separator reutilizado fica ~4,5x mais lento
    a partir da 2ª música (e carregar o modelo custa só ~2 s)."""
    os.makedirs(out_dir, exist_ok=True)
    err = '?'
    for _ in range(3):   # às vezes a GPU devolve lixo (sobretudo na 1ª chamada logo após outro processo): tenta de novo
        r = subprocess.run([sys.executable, '-m', 'yl.align', '--uvr', model, mix, out_dir],
                           cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        lines = [l for l in r.stdout.splitlines() if l.startswith('UVR_OUT ')]
        if not r.returncode and lines:
            return lines[-1][8:]
        err = (r.stderr.strip().splitlines() or ['?'])[-1][:200]
    raise RuntimeError('separador falhou: ' + err)

def _uvr_vocals_inproc(model, mix, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    if model not in _uvr:   # carrega o modelo uma vez por processo
        import logging
        from audio_separator.separator import Separator
        kw = {}
        if os.environ.get('YL_SEP_OVERLAP'):   # padrão da biblioteca (8); valores menores deixam MAIS lento no Roformer
            kw['mdxc_params'] = {'segment_size': 256, 'override_model_segment_size': False, 'batch_size': 1,
                                 'overlap': int(os.environ['YL_SEP_OVERLAP']), 'pitch_shift': 0}
        s = Separator(model_file_dir=MODELS_DIR, output_dir=out_dir, output_single_stem='Vocals',
                      output_format='WAV', log_level=logging.WARNING, **kw)
        s.load_model(model_filename=model)
        _uvr[model] = s
    s = _uvr[model]
    s.output_dir = out_dir
    if getattr(s, 'model_instance', None) is not None:
        s.model_instance.output_dir = out_dir
    files = s.separate(mix, custom_output_names={'Vocals': 'vocals'})
    p = os.path.join(out_dir, os.path.basename(files[0]))
    p = p if os.path.exists(p) else files[0]
    # GPU em estado ruim (ex.: depois de um processo morto no meio) devolve lixo rápido em vez de erro
    # (saída sem relação com a entrada: correlação ~0 com o mix; voz de verdade dá >0.1)
    v, _ = sf.read(p, dtype='float32')
    m, _ = sf.read(mix, dtype='float32')
    v, m = v.reshape(len(v), -1).mean(1), m.reshape(len(m), -1).mean(1)
    n = min(len(v), len(m))
    corr = float(np.corrcoef(v[:n], m[:n])[0, 1]) if n and v[:n].std() > 0 else 0.0
    if not np.isfinite(v).all() or not corr > 0.05:
        raise RuntimeError(f'saída inválida do separador (correlação com o mix {corr:+.3f})')
    return p

# ---------------------------------------------------------------- modelo
_bundle = torchaudio.pipelines.MMS_FA
_model = None

_models = {}

def _get_model():
    """Modelo CTC do aligner atual (YL_ALIGNER / aligners.using; ver yl/aligners.py), carregado uma vez."""
    from yl import aligners
    k = aligners.name()
    if k not in _models:
        torch.set_num_threads(max(1, os.cpu_count() - 1))
        _models[k] = aligners.load(DEVICE)
    return _models[k][0]

def _tokenizer():
    from yl import aligners
    _get_model()
    return _models[aligners.name()][1]

def debias(raw):
    """Desconta o viés médio do aligner atual (tempo de áudio, antes do finalize)."""
    from yl import aligners
    b = aligners.BIAS.get(aligners.name(), 0.0)
    for p in raw:
        for w in p['words']:
            if w.get('t') is not None:
                w['t'] -= b
            if w.get('end') is not None:
                w['end'] -= b
    return raw

def consensus_lrc(raw1, raw2, thr=0.5):
    """Por linha: se os dois aligners discordam > thr s no início, fica o que está mais perto do tempo do LRCLIB.
    No gabarito (inglês): linhas ruins 5,8% (w2v) -> 5,3% com o ALT-DSing como 2ª opinião."""
    if len(raw1) != len(raw2) or any(len(a['words']) != len(b['words']) for a, b in zip(raw1, raw2)):
        return raw1, 0
    out, n = [], 0
    for a, b in zip(raw1, raw2):
        lrc = a.get('lrc_t')
        sa, sb = a['words'][0]['t'], b['words'][0]['t']
        dis = abs(sa - sb) if sa is not None and sb is not None else None
        if lrc is not None and dis is not None and dis > thr and abs(sb - lrc) < abs(sa - lrc):
            out.append(dict(a, words=b['words'], dis=dis)); n += 1
        else:
            out.append(dict(a, dis=dis))
    return out, n

def emission(wav_path, chunk_s=30, ctx_s=2):
    wav, sr = sf.read(wav_path, dtype='float32')
    wav = torch.from_numpy(wav)
    model = _get_model()
    n = wav.shape[0]
    hop = 320  # 20 ms por frame
    total_frames = n // hop
    out = []
    with torch.inference_mode():
        s = 0
        while s < n:
            e = min(n, s + chunk_s * SR)
            a, b = max(0, s - ctx_s * SR), min(n, e + ctx_s * SR)
            em, _ = model(wav[a:b].unsqueeze(0).to(DEVICE))
            em = em[0].float().cpu()
            f0 = (s - a) // hop
            f1 = f0 + (e - s) // hop
            out.append(em[f0:min(f1, em.shape[0])])
            s = e
    em = torch.cat(out)
    free_gpu_cache()
    ratio = n / SR / em.shape[0]
    _voice_stats(em, wav.numpy(), ratio)
    return em, ratio, n / SR

# ---------------------------------------------------------------- atividade vocal
LAST_STATS = {}

def _voice_stats(em, wav, ratio):
    # fração de janelas de 1 s com fala/canto (pelo CTC) e com energia no stem de voz
    pb = torch.softmax(em.float(), -1)[:, 0].numpy()
    win = max(1, int(round(1.0 / ratio)))
    nw = len(pb) // win
    mx = (1 - pb[:nw * win]).reshape(nw, win).max(1) if nw else np.zeros(1)
    ch = SR // 2
    nc = len(wav) // ch
    rms = np.sqrt((wav[:nc * ch].reshape(nc, ch) ** 2).mean(1)) if nc else np.zeros(1)
    db = 20 * np.log10(rms + 1e-9)
    g = em[:, :-1].argmax(-1).numpy()                      # exclui o '*' (última classe)
    voiced = g != 0
    cnt = voiced[:nw * win].reshape(nw, win).sum(1) if nw else np.zeros(1)
    LAST_STATS.clear()
    LAST_STATS.update(chars_per_s=round(float(voiced.sum() / max(1, len(g)) / ratio), 2),
                      voiced_win_frac=round(float((cnt >= 2).mean()), 3))
    LAST_STATS.update(speech_win_frac=round(float((mx > 0.5).mean()), 3),
                      vocal_rms_frac=round(float((db > -40).mean()), 3))

# ---------------------------------------------------------------- texto
_dict = _bundle.get_dict(star='*')

def _num_words(w, lang):
    try:
        from num2words import num2words
        return num2words(int(w), lang='pt_BR' if lang == 'pt' else 'en')
    except Exception:
        return ''

def norm_word(w, lang):
    s = w
    if re.fullmatch(r'\d+', re.sub(r'\W', '', s) or 'x'):
        s = _num_words(re.sub(r'\W', '', s), lang)
    s = unicodedata.normalize('NFD', s.lower())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.replace('ç', 'c')
    return ''.join(c for c in s if c in _dict and c not in ('-', '*'))

# ---------------------------------------------------------------- alinhamento
def align(lines, wav_path, lang):
    """lines: [{'t':s|None,'words':[str]}]. Retorna frases com tempo por palavra (tempo de áudio)."""
    em, ratio, dur = emission(wav_path)
    em = torch.log_softmax(em, dim=-1)
    tokenizer, aligner = _tokenizer(), _bundle.get_aligner()
    flat, owner = ['*'], [None]
    for li, l in enumerate(lines):
        for wi, w in enumerate(l['words']):
            nw = norm_word(w, lang)
            if nw:
                flat.append(nw); owner.append((li, wi))
        flat.append('*'); owner.append(None)
    spans = aligner(em, tokenizer(flat))
    times = {}
    for sp, ow in zip(spans, owner):
        if ow is None:
            continue
        times[ow] = (sp[0].start * ratio, sp[-1].end * ratio,
                     float(np.mean([x.score for x in sp])))
    phrases = []
    for li, l in enumerate(lines):
        words = []
        for wi, w in enumerate(l['words']):
            t = times.get((li, wi))
            words.append({'text': w, 't': t[0] if t else None, 'end': t[1] if t else None,
                          'score': t[2] if t else None})
        known = [i for i, w in enumerate(words) if w['t'] is not None]
        if not known:
            continue
        for i, w in enumerate(words):  # interpola palavras sem tokens (ex.: só símbolos)
            if w['t'] is None:
                prv = max([k for k in known if k < i], default=None)
                nxt = min([k for k in known if k > i], default=None)
                if prv is not None and nxt is not None:
                    w['t'] = words[prv]['end'] + (words[nxt]['t'] - words[prv]['end']) * 0.5
                else:
                    w['t'] = words[prv]['end'] if prv is not None else words[nxt]['t'] - 0.1
                w['end'] = w['t'] + 0.1
        phrases.append({'lrc_t': l['t'], 'words': words})
    return phrases, dur

def fix_bounds(out, gap=0.05):
    """Garante palavras em ordem (também entre frases) e frases que sempre contêm as próprias palavras.

    Se o alinhador pôs a 1ª palavra de uma linha antes da última da linha anterior, ela é empurrada
    para logo depois; o fim de cada frase nunca passa do início da seguinte.
    """
    last = None
    for ph in out:
        for w in ph['words']:
            if last is not None and w['t'] < last + gap:
                w['t'] = last + gap
            w['end'] = max(w.get('end') or w['t'] + 0.1, w['t'] + 0.05)
            last = w['t']
    for k, ph in enumerate(out):
        ws = ph['words']
        ph['start'] = min(ph.get('start', ws[0]['t'] - 0.15), ws[0]['t'] - 0.01)
        ph['end'] = max(ph.get('end', ws[-1]['end'] + 0.25), ws[-1]['t'] + 0.05)
    for a, b in zip(out, out[1:]):
        if a['end'] > b['start'] - 0.02:
            fa, lb = a['words'][-1]['t'], b['words'][0]['t']
            cut = max(fa + 0.03, min(a['end'], (a['words'][-1]['end'] + lb) / 2, lb - 0.03))
            a['end'] = min(cut, lb - 0.02)
            b['start'] = max(a['end'] + 0.01, min(b['start'], lb - 0.01))
            b['start'] = min(b['start'], lb - 0.005)
    for ph in out:
        ph['start'] = max(0.0, ph['start'])
    return out

def finalize(phrases, delay):
    """Converte p/ tempo de chart e define início/fim de frase sem sobreposição."""
    out = []
    for ph in phrases:
        ws = [{'t': w['t'] - delay, 'text': w['text'], 'end': w['end'] - delay, 'score': w['score']}
              for w in ph['words']]
        out.append({'start': ws[0]['t'] - 0.15, 'end': max(w['end'] for w in ws) + 0.25,
                    'words': ws, 'lrc_t': ph['lrc_t']})
        if ph.get('dis') is not None:                    # discordância entre os 2 aligners (s), p/ as suspeitas
            out[-1]['dis'] = round(ph['dis'], 3)
    return fix_bounds(out)

def quality(phrases, delay):
    sc = [w['score'] for p in phrases for w in p['words'] if w['score'] is not None]
    offs = [p['words'][0]['t'] + delay - p['lrc_t'] for p in phrases if p['lrc_t'] is not None]
    q = {'mean_score': round(float(np.mean(sc)), 3) if sc else 0,
         'low_score_frac': round(float(np.mean([s < 0.2 for s in sc])), 3) if sc else 1}
    if offs:
        med = statistics.median(offs)
        q['lrc_offset_s'] = round(med, 2)
        q['lrc_disagree_frac'] = round(float(np.mean([abs(o - med) > 1.5 for o in offs])), 3)
    return q


# ================================================================ v2: alinhamento ancorado por linha
def _activity(em):
    """Probabilidade de 'tem fala' por frame (1 - P(blank)), suavizada ~200 ms."""
    p = 1.0 - torch.exp(em[:, 0]).numpy()
    k = np.ones(10) / 10
    return np.convolve(p, k, mode='same')

def estimate_offset(lines, act, ratio, search=30.0, step=0.05):
    """Acha o deslocamento (s) que melhor encaixa as linhas do LRC na atividade vocal."""
    ts = [l['t'] for l in lines]
    n = len(act)
    scores = []
    a = act - act.mean()
    for o in np.arange(-search, search + 1e-9, step):
        mask = np.zeros(n)
        for i, l in enumerate(lines):
            nxt = ts[i + 1] if i + 1 < len(ts) else ts[i] + 6
            dur = min(nxt - ts[i], 0.45 * len(l['words']) + 0.5)
            f0, f1 = int((ts[i] + o) / ratio), int((ts[i] + o + dur) / ratio)
            if f1 > 0 and f0 < n:
                mask[max(0, f0):min(n, f1)] = 1
        s = float((a * mask).sum())
        scores.append((s, float(o)))
    # devolve os melhores picos locais (candidatos) + 0
    scores.sort(reverse=True)
    cands = [0.0]
    for s, o in scores:
        if all(abs(o - c) > 1.0 for c in cands):
            cands.append(o)
        if len(cands) >= 6:
            break
    return cands

def align_anchored(lines, wav_path, lang, pre=1.2, post=0.8):
    em, ratio, dur = emission(wav_path)
    em = torch.log_softmax(em, dim=-1)
    tokenizer, aligner = _tokenizer(), _bundle.get_aligner()
    act = _activity(em)
    T = em.shape[0]
    best = None
    for off in estimate_offset(lines, act, ratio):
        ph = _align_lines(lines, em, ratio, dur, T, off, lang, tokenizer, aligner, pre, post)
        sc = [w['score'] for p in ph for w in p['words'] if w['score'] is not None]
        m = float(np.mean(sc)) if sc else 0.0
        if best is None or m > best[0]:
            best = (m, ph, off)
    return best[1], dur, best[2]

def _align_lines(lines, em, ratio, dur, T, off, lang, tokenizer, aligner, pre, post):
    phrases = []
    prev_end = 0.0
    for li, l in enumerate(lines):
        t0 = l['t'] + off - pre
        t1 = (lines[li + 1]['t'] + off + post) if li + 1 < len(lines) else min(dur, l['t'] + off + 12)
        idx, toks = [], []
        for wi, w in enumerate(l['words']):
            nw = norm_word(w, lang)
            if nw:
                idx.append(wi); toks.append(nw)
        if not toks:
            continue
        need = sum(len(x) for x in toks) * 2 + 4
        t0 = max(t0, prev_end + 0.02)          # não reaproveita o áudio da linha anterior
        f0, f1 = max(0, int(t0 / ratio)), min(T, int(t1 / ratio))
        if f1 - f0 < need:
            f1 = min(T, f0 + need)
        try:
            spans = aligner(em[f0:f1], tokenizer(['*'] + toks + ['*']))[1:-1]
        except Exception:
            continue
        words = [{'text': w, 't': None, 'end': None, 'score': None} for w in l['words']]
        for wi, sp in zip(idx, spans):
            words[wi].update(t=(f0 + sp[0].start) * ratio, end=(f0 + sp[-1].end) * ratio,
                             score=float(np.mean([x.score for x in sp])))
        known = [i for i, w in enumerate(words) if w['t'] is not None]
        for i, w in enumerate(words):
            if w['t'] is None:
                prv = max([k for k in known if k < i], default=None)
                nxt = min([k for k in known if k > i], default=None)
                if prv is not None and nxt is not None:
                    w['t'] = (words[prv]['end'] + words[nxt]['t']) / 2
                else:
                    w['t'] = words[prv]['end'] if prv is not None else words[nxt]['t'] - 0.1
                w['end'] = w['t'] + 0.1
        prev_end = max(prev_end, max(w['end'] for w in words if w['end'] is not None))
        phrases.append({'lrc_t': l['t'] + off, 'words': words, 'li': li})
    return phrases


# ================================================================ v3: refinamento híbrido
def _line_score(p):
    sc = [w['score'] for w in p['words'] if w['score'] is not None]
    return float(np.mean(sc)) if sc else 0.0

def _align_block(block_lines, em, ratio, f0, f1, lang, tokenizer, aligner):
    """Alinha várias linhas juntas (com '*' entre elas) dentro de em[f0:f1]."""
    flat, owner = ['*'], [None]
    for li, l in enumerate(block_lines):
        for wi, w in enumerate(l['words']):
            nw = norm_word(w, lang)
            if nw:
                flat.append(nw); owner.append((li, wi))
        flat.append('*'); owner.append(None)
    if f1 - f0 < sum(len(x) for x in flat) * 2 + 4:
        return None
    try:
        spans = aligner(em[f0:f1], tokenizer(flat))
    except Exception:
        return None
    res = [[{'text': w, 't': None, 'end': None, 'score': None} for w in l['words']] for l in block_lines]
    for sp, ow in zip(spans, owner):
        if ow is not None:
            li, wi = ow
            res[li][wi].update(t=(f0 + sp[0].start) * ratio, end=(f0 + sp[-1].end) * ratio,
                               score=float(np.mean([x.score for x in sp])))
    out = []
    for words in res:
        known = [i for i, w in enumerate(words) if w['t'] is not None]
        if not known:
            return None
        for i, w in enumerate(words):
            if w['t'] is None:
                k = min(known, key=lambda k: abs(k - i))
                w['t'] = words[k]['t']; w['end'] = w['t'] + 0.1
        out.append(words)
    return out

LAST_STATS_EXTRA = {}

def _repair_glued(ph, lines, em, ratio, dur, lang, tokenizer, aligner, post):
    """Linhas coladas na anterior (folga < 0,05 s) e > 0,5 s antes da âncora do LRC costumam estar erradas
    (54% no gabarito): o alinhador encostou a linha no fim da anterior. Realinha a linha numa janela que começa
    na âncora; aceita se a confiança não cair muito."""
    n = 0
    for k in range(1, len(ph)):
        p, prev = ph[k], ph[k - 1]
        if p.get('lrc_t') is None or 'li' not in p:
            continue
        first = p['words'][0]['t']
        prev_end = max((w.get('end') or w['t']) for w in prev['words'])
        if not (first - prev_end < 0.05 and first - p['lrc_t'] < -0.5):
            continue
        t0 = max(prev_end + 0.02, p['lrc_t'] - 0.3)
        t1 = (ph[k + 1]['lrc_t'] + post) if k + 1 < len(ph) and ph[k + 1].get('lrc_t') is not None else min(dur, p['lrc_t'] + 12)
        blk = _align_block([lines[p['li']]], em, ratio, int(t0 / ratio), int(t1 / ratio), lang, tokenizer, aligner)
        if not blk:
            continue
        ws = blk[0]
        new = np.mean([w['score'] for w in ws if w['score'] is not None] or [0])
        if new >= 0.8 * _line_score(p) and (k + 1 >= len(ph) or ws[-1]['t'] < ph[k + 1]['words'][0]['t']):
            p['words'] = ws
            n += 1
    return ph, n

def align_hybrid(lines, wav_path, lang, good_thr=0.25, pre=1.2, post=0.8):
    em, ratio, dur = emission(wav_path)
    em = torch.log_softmax(em, dim=-1)
    tokenizer, aligner = _tokenizer(), _bundle.get_aligner()
    T = em.shape[0]
    act = _activity(em)
    best = None
    for off in estimate_offset(lines, act, ratio):
        ph = _align_lines(lines, em, ratio, dur, T, off, lang, tokenizer, aligner, pre, post)
        sc = [w['score'] for p in ph for w in p['words'] if w['score'] is not None]
        m = float(np.mean(sc)) if sc else 0.0
        if best is None or m > best[0]:
            best = (m, ph, off)
    _, ph, off = best
    # linhas sem tokens foram descartadas em _align_lines; reindexa pelas que sobraram
    kept = [lines[p['li']] for p in ph]
    good = [_line_score(p) >= good_thr for p in ph]
    # âncoras precisam ser monotônicas
    last = -1.0
    for i, p in enumerate(ph):
        if good[i]:
            if p['words'][0]['t'] <= last:
                good[i] = False
            else:
                last = p['words'][-1]['end']
    fixed, i = 0, 0
    while i < len(ph):
        if good[i]:
            i += 1; continue
        j = i
        while j < len(ph) and not good[j]:
            j += 1
        r0 = ph[i - 1]['words'][-1]['end'] + 0.05 if i > 0 else 0.0
        r1 = ph[j]['words'][0]['t'] - 0.05 if j < len(ph) else dur
        blk = _align_block(kept[i:j], em, ratio, int(r0 / ratio), int(r1 / ratio), lang, tokenizer, aligner)
        if blk is not None:
            old = np.mean([_line_score(p) for p in ph[i:j]])
            new = np.mean([np.mean([w['score'] for w in ws if w['score'] is not None] or [0]) for ws in blk])
            if new > old:
                for k, ws in enumerate(blk):
                    ph[i + k]['words'] = ws
                fixed += j - i
        i = j
    ph, nrep = _repair_glued(ph, lines, em, ratio, dur, lang, tokenizer, aligner, post)
    LAST_STATS_EXTRA['lines_repaired'] = nrep
    return ph, dur, off, fixed


# ================================================================ métricas de confiança e veredito
_quality_v1 = quality

def quality(phrases, delay):
    q = _quality_v1(phrases, delay)
    ls = [_line_score(p) for p in phrases]
    q['bad_line_frac'] = round(float(np.mean([s < 0.15 for s in ls])), 3) if ls else 1.0
    fl = line_flags(phrases, delay)
    for ph, f in zip(phrases, fl):
        ph['flag'] = f
    q['suspect_hi_frac'] = round(float(np.mean([f == 2 for f in fl])), 3) if fl else 0.0
    q['suspect_any_frac'] = round(float(np.mean([f >= 1 for f in fl])), 3) if fl else 0.0
    q['median_line_score'] = round(float(np.median(ls)), 3) if ls else 0.0
    return q

# Veredito: calibrado em 57 músicas (gabarito com letra feita à mão, voz separada pelo Demucs).
# REVISAR se >12% das linhas têm suspeita alta (pega a maioria das músicas com >15% de linhas erradas,
# 4 alarmes falsos em 57), ou se a letra do LRCLIB claramente não é desta versão.
VERDICT = {'max_suspect_hi_frac': 0.12, 'max_lrc_disagree_frac': 0.40,
           'max_duration_delta_s': 8.0, 'dd_disagree_frac': 0.25}

def verdict(rep):
    q, V = rep.get('quality', {}), VERDICT
    d = q.get('lrc_disagree_frac', 0)
    dd = (rep.get('lrclib') or {}).get('duration_delta_s', 0)
    # padrão novo (w2v-960h + regras novas): o mesmo 0,12 pega 5 de 7 músicas ruins, 23 de 57 p/ revisar
    if q.get('suspect_hi_frac', 0) > V['max_suspect_hi_frac'] or d > V['max_lrc_disagree_frac']:
        return 'REVISAR'
    if dd > V['max_duration_delta_s'] and d > V['dd_disagree_frac']:
        return 'REVISAR'
    return 'ok'


# instrumental: quase nenhum caractere reconhecido pelo CTC na voz separada, ou stem de voz mudo.
# Energia do stem sozinha NÃO serve: vozes fracas de rips do GH3 (One, Raining Blood) ficam abaixo de 0.3.
# Calibrado: menor cps entre 80+ músicas com voz = 0.53; instrumentais do GH3 <= 0.47.
INSTRUMENTAL = {'max_chars_per_s': 0.5, 'max_voiced_win_frac': 0.15, 'mute_vocal_rms_frac': 0.05}

def is_instrumental(q):
    T = INSTRUMENTAL
    if 'chars_per_s' not in q:
        return False
    if q.get('vocal_rms_frac', 1) < T['mute_vocal_rms_frac']:
        return True
    if q.get('vocal_rms_frac', 0) > 0.5 and q['chars_per_s'] > 0.4:   # voz forte no stem, só pouco texto (ex.: Priestess - Lay Down)
        return False
    return q['chars_per_s'] < T['max_chars_per_s'] and q.get('voiced_win_frac', 1) < T['max_voiced_win_frac']


# ================================================================ suspeita por linha
# Calibrado em 2041 linhas de 57 músicas com letra feita à mão (tools/line_quality.py):
#   nível 2 (alta)  -> 70% das linhas assim estão erradas (>0,5 s); cobre 77% das linhas erradas
#   nível 1 (média) -> 14% erradas;   nível 0 -> 3% erradas
def line_flags(phrases, delay=0.0):
    from yl import aligners
    new_rules = aligners.name() != 'mms'          # regras antigas foram calibradas com os scores do MMS
    out = []
    for k, p in enumerate(phrases):
        ws = p['words']
        first = ws[0]['t']
        last_end = max((w.get('end') or w['t']) for w in ws)
        dur = max(0.05, last_end - first)
        lrc = p.get('lrc_t')
        nxt = phrases[k + 1].get('lrc_t') if k + 1 < len(phrases) else None
        lrc_dur = min(8.0, nxt - lrc) if (lrc is not None and nxt is not None and nxt > lrc) else None
        ratio = dur / lrc_dur if lrc_dur else None
        dev = abs(first + delay - lrc) if lrc is not None else 0.0
        sc = [w['score'] for w in ws if w.get('score') is not None]
        if not sc:                          # sem métricas (ex.: linha ajustada à mão)
            out.append(0); continue
        score = float(np.mean(sc))
        cps = sum(len(norm_word(w['text'], 'pt')) for w in ws) / dur
        gap = first - max((w.get('end') or w['t']) for w in phrases[k - 1]['words']) if k else None
        sdev = (first + delay - lrc) if lrc is not None else 0.0
        if new_rules:
            # calibrado no gabarito p/ w2v-960h (+ALT-DSing): nível 2 = 7% das linhas, 27% delas ruins, cobre 37% das ruins;
            # sem flag: 2,6% ruins. 'dis' = discordância entre os 2 aligners (só quando houve 2ª opinião)
            dis = p.get('dis')
            if (dis is not None and dis > 0.8) or dev > 3 or (ratio is not None and ratio > 1.5) or cps > 30 or \
                    (gap is not None and gap < 0.02):
                out.append(2)
            elif score < 0.05 or (dis is not None and dis > 0.3) or dev > 2 or cps < 4:
                out.append(1)
            else:
                out.append(0)
            continue
        glued_early = gap is not None and gap < 0.05 and sdev < -0.5      # 54% erradas no gabarito
        if dev > 2 or (ratio is not None and ratio > 1.5) or cps > 30 or glued_early or \
                (score < 0.03 and ratio is not None and ratio < 0.5):
            out.append(2)
        elif score < 0.03 or (ratio is not None and ratio < 0.3) or cps < 4 or cps > 18 or (gap is not None and gap < 0.05 and score < 0.06):
            out.append(1)
        else:
            out.append(0)
    return out


if __name__ == '__main__' and len(sys.argv) == 5 and sys.argv[1] == '--uvr':
    # worker do separador (ver _uvr_vocals): python -m yl.align --uvr <modelo> <mix.wav> <pasta_saida>
    print('UVR_OUT ' + _uvr_vocals_inproc(*sys.argv[2:5]), flush=True)
