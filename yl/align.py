"""Separação de voz (Demucs) + alinhamento forçado por palavra (MMS_FA, multilíngue)."""
import os, re, subprocess, sys, shutil, statistics, unicodedata
import numpy as np
import torch, torchaudio
import soundfile as sf

SR = 16000
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
    out = os.path.join(cache, 'vocals16k.wav')
    if os.path.exists(out):
        return out, 'cache'
    all_stems = stems(folder)
    voc = [p for p in all_stems if os.path.basename(p).lower().startswith('vocals')]
    if voc:
        _ffmpeg_decode(voc, out, SR, True)
        return out, 'stem'
    mix = os.path.join(cache, 'mix.wav')
    _ffmpeg_decode(all_stems, mix, 44100, False)
    subprocess.run([sys.executable, '-m', 'demucs', '--two-stems=vocals', '-n', 'htdemucs',
                    '-o', os.path.join(cache, 'demucs'), mix], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    dv = os.path.join(cache, 'demucs', 'htdemucs', 'mix', 'vocals.wav')
    _ffmpeg_decode([dv], out, SR, True)
    os.remove(mix)
    shutil.rmtree(os.path.join(cache, 'demucs'), ignore_errors=True)
    return out, 'demucs'

# ---------------------------------------------------------------- modelo
_bundle = torchaudio.pipelines.MMS_FA
_model = None

def _get_model():
    global _model
    if _model is None:
        torch.set_num_threads(max(1, os.cpu_count() - 1))
        _model = _bundle.get_model(with_star=True).eval()
    return _model

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
            em, _ = model(wav[a:b].unsqueeze(0))
            em = em[0]
            f0 = (s - a) // hop
            f1 = f0 + (e - s) // hop
            out.append(em[f0:min(f1, em.shape[0])])
            s = e
    em = torch.cat(out)
    return em, n / SR / em.shape[0], n / SR

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
    tokenizer, aligner = _bundle.get_tokenizer(), _bundle.get_aligner()
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

def finalize(phrases, delay):
    """Converte p/ tempo de chart e define início/fim de frase sem sobreposição."""
    out = []
    for i, ph in enumerate(phrases):
        ws = [{'t': w['t'] - delay, 'text': w['text'], 'end': w['end'] - delay, 'score': w['score']}
              for w in ph['words']]
        for j in range(1, len(ws)):            # garante ordem estrita
            ws[j]['t'] = max(ws[j]['t'], ws[j - 1]['t'] + 0.02)
        out.append({'start': ws[0]['t'] - 0.15, 'end': max(w['end'] for w in ws) + 0.25,
                    'words': ws, 'lrc_t': ph['lrc_t']})
    for a, b in zip(out, out[1:]):
        if a['end'] > b['start'] - 0.02:
            mid = (a['words'][-1]['end'] + b['words'][0]['t']) / 2
            a['end'] = max(a['words'][-1]['t'] + 0.05, min(a['end'], mid))
            b['start'] = max(a['end'] + 0.01, min(b['start'], b['words'][0]['t'] - 0.01))
    for ph in out:
        ph['start'] = max(0.0, ph['start'])
    return out

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
    tokenizer, aligner = _bundle.get_tokenizer(), _bundle.get_aligner()
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

def align_hybrid(lines, wav_path, lang, good_thr=0.25, pre=1.2, post=0.8):
    em, ratio, dur = emission(wav_path)
    em = torch.log_softmax(em, dim=-1)
    tokenizer, aligner = _bundle.get_tokenizer(), _bundle.get_aligner()
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
    return ph, dur, off, fixed


# ================================================================ métricas de confiança e veredito
_quality_v1 = quality

def quality(phrases, delay):
    q = _quality_v1(phrases, delay)
    ls = [_line_score(p) for p in phrases]
    q['bad_line_frac'] = round(float(np.mean([s < 0.15 for s in ls])), 3) if ls else 1.0
    q['median_line_score'] = round(float(np.median(ls)), 3) if ls else 0.0
    return q

# limiares calibrados em 17 músicas (6 pt + 11 en) com letra de referência — ver tools/calibrate.py
# Pegou todas as claramente ruins (>15% das palavras com erro >1 s); falsos positivos aceitáveis.
VERDICT = {'max_lrc_disagree_frac': 0.40, 'min_mean_score': 0.10, 'max_duration_delta_s': 8.0}

def verdict(rep):
    q = rep.get('quality', {})
    if rep.get('lrclib') and rep['lrclib']['duration_delta_s'] > VERDICT['max_duration_delta_s']:
        return 'REVISAR'
    if q.get('lrc_disagree_frac', 0) > VERDICT['max_lrc_disagree_frac']:
        return 'REVISAR'
    if q.get('mean_score', 0) < VERDICT['min_mean_score']:
        return 'REVISAR'
    return 'ok'
