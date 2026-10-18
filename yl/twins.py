"""Detecta versões com o MESMO áudio (ex.: Co-op, Career, rips repetidos) e a defasagem entre elas.

Impressão digital = fluxo espectral (ataques) a 100 quadros/s do mix de todos os stems.
Duas versões são "iguais" se, depois de achar a defasagem global, quase todas as janelas de 15 s
concordam com essa mesma defasagem (então uma letra pode ser copiada só deslocando o tempo).
"""
import os, re, json, subprocess, unicodedata
import numpy as np
from yl import align, charts

FPS = 100
SR = 16000
HOP = SR // FPS

def _decode_mix(folder):
    st = align.stems(folder)
    if not st:
        return None
    cmd = ['ffmpeg', '-v', 'error']
    for p in st:
        cmd += ['-i', p]
    if len(st) > 1:
        cmd += ['-filter_complex', f'amix=inputs={len(st)}:normalize=0:duration=longest']
    cmd += ['-ac', '1', '-ar', str(SR), '-f', 's16le', '-']
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

def fingerprint(folder, cache_dir):
    p = os.path.join(cache_dir, 'fp_flux.npy')
    if os.path.exists(p):
        return np.load(p)
    x = _decode_mix(folder)
    if x is None or len(x) < SR:
        return None
    n = 512
    frames = np.lib.stride_tricks.sliding_window_view(x, n)[::HOP]
    mag = np.log1p(np.abs(np.fft.rfft(frames * np.hanning(n), axis=1)))
    flux = np.maximum(np.diff(mag, axis=0), 0).sum(axis=1)
    flux = np.convolve(flux, np.ones(3) / 3, mode='same').astype(np.float32)
    np.save(p, flux)
    return flux

def _z(v):
    s = v.std()
    return (v - v.mean()) / s if s > 1e-9 else v * 0

def compare(fa, fb, max_off_s=40.0, win_s=15.0):
    """Retorna dict(offset_s, match_frac, windows, corr). offset: t_b = t_a + offset."""
    a, b = _z(fa), _z(fb)
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    xc = np.fft.irfft(np.fft.rfft(b, n) * np.conj(np.fft.rfft(a, n)), n)
    lag_max = int(max_off_s * FPS)
    lags = np.r_[np.arange(0, lag_max + 1), np.arange(-lag_max, 0)]
    vals = np.r_[xc[:lag_max + 1], xc[-lag_max:]]
    lag = int(lags[np.argmax(vals)])
    corr = float(vals.max() / min(len(a), len(b)))
    w = int(win_s * FPS)
    ok = tot = 0
    for s in range(0, len(a) - w, w):
        seg = a[s:s + w]
        if seg.std() < 1e-6:
            continue
        best, best_l = -1.0, 0
        for l in range(lag - 50, lag + 51, 2):          # procura ±0,5 s em volta da defasagem global
            t = s + l
            if t < 0 or t + w > len(b):
                continue
            c = float(np.dot(_z(seg), _z(b[t:t + w])) / w)
            if c > best:
                best, best_l = c, l
        if best < 0:
            continue
        tot += 1
        if best > 0.5 and abs(best_l - lag) <= 3:
            ok += 1
    return {'offset_s': round(lag / FPS, 3), 'match_frac': round(ok / tot, 3) if tot else 0.0,
            'windows': tot, 'corr': round(corr, 3),
            'len_a_s': round(len(fa) / FPS, 1), 'len_b_s': round(len(fb) / FPS, 1)}

def verdict(cmp):
    if cmp['windows'] >= 4 and cmp['match_frac'] >= 0.9:
        return 'igual'
    if cmp['match_frac'] >= 0.6:
        return 'parecido'
    return 'diferente'

# ---------------------------------------------------------------- agrupamento por nome
_SUF = re.compile(r'[\(\[][^)\]]*(co-?op|career|version|vers[aã]o|remaster|gh brazucas|rb3|harmonix)[^)\]]*[\)\]]', re.I)

def norm_title(s):
    s = unicodedata.normalize('NFD', s or '')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    s = _SUF.sub('', s)
    s = re.sub(r'\b(j\.h\.?|k\.h\.?)$', '', s.strip())
    s = s.replace('&', ' and ')
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()

def norm_artist(s):
    s = re.sub(r'\(.*?\)', '', s or '')
    return re.sub(r'^the ', '', norm_title(s))

def key(folder):
    ini = charts.read_ini(folder)
    return norm_artist(ini.get('artist', '')), norm_title(ini.get('name', '') or os.path.basename(folder))
