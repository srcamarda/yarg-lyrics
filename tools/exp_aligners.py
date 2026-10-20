"""Compara aligners (MMS, ALT-DSing, ALT-DALI, wav2vec2-960h, Whisper) e consensos entre eles, por idioma. Só números.

Usa os aligned_eval_<tag>.json / aligned_whisper_<tag>.json guardados no cache (voz do mix pelo RoFormer).
Uso: python tools/exp_aligners.py [--json saida.json]
"""
import sys, os, json, statistics
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from run import cache_dir
from yl import charts
from exp_eval import song_metrics, summarize, shift, snap, line_start

BASE = 'mix_vocals_mel_band_roformer'
MODELS = {'MMS': f'aligned_eval_{BASE}.json', 'ALT-DSing': f'aligned_eval_{BASE}_altdsing.json',
          'ALT-DALI': f'aligned_eval_{BASE}_altdali.json', 'w2v-960h': f'aligned_eval_{BASE}_w2v960h.json',
          'Whisper': f'aligned_whisper_{BASE}.json'}

def same_shape(a, b):
    return len(a) == len(b) and all(len(x['words']) == len(y['words']) for x, y in zip(a, b))

def pick_lrc(cands, thr=0.5):
    """Por linha: se algum candidato discorda do primeiro em > thr no início, fica o mais perto do tempo do LRCLIB."""
    base = cands[0]
    if any(not same_shape(base, c) for c in cands[1:]):
        return None
    out = []
    for k, p in enumerate(base):
        lrc = p.get('lrc_t')
        starts = [line_start(c[k]) for c in cands]
        if lrc is not None and max(abs(s - starts[0]) for s in starts) > thr:
            j = min(range(len(cands)), key=lambda j: abs(starts[j] - lrc))
            out.append(cands[j][k])
        else:
            out.append(p)
    return out

folders = json.load(open(os.path.join(ROOT, 'gold_all.json'), encoding='utf-8-sig'))
songs = []
for f in folders:
    cd = cache_dir(f)
    d = {}
    for m, fn in MODELS.items():
        p = os.path.join(cd, fn)
        if os.path.exists(p):
            j = json.load(open(p, encoding='utf-8'))
            d[m] = j['phrases']
            if 'lang' in j:
                d['_lang'] = j['lang']
    if 'MMS' not in d:
        continue
    ch = charts.open_chart(f)
    d['_ref'] = charts.lyric_events_to_words(ch.read_lyrics()[0], ch.tmap)
    d['_tmap'] = ch.tmap
    songs.append(d)

# viés mediano de cada modelo (medido neste conjunto; usado só nas variantes "corrigidas")
bias = {}
for m in MODELS:
    errs = [e for s in songs if m in s for e in (song_metrics(s['_ref'], s[m]) or {'signed': []})['signed']]
    bias[m] = statistics.median(errs) if errs else 0.0

def variants(s):
    v = {}
    for m in MODELS:
        if m in s:
            v[m] = s[m]
            v[f'{m} (viés corrigido)'] = shift(s[m], -bias[m])
    fix = {m: shift(s[m], -bias[m]) for m in MODELS if m in s}
    en = s.get('_lang') == 'en'
    for m in ('ALT-DSing', 'ALT-DALI', 'w2v-960h'):
        if m in fix:                                  # modelo inglês só nas músicas em inglês; resto fica MMS
            v[f'{m} só em inglês (corr.)'] = fix[m] if en else fix['MMS']
    combos = {'MMS×Whisper': ['MMS', 'Whisper'], 'MMS×ALT-DSing': ['MMS', 'ALT-DSing'],
              'MMS×ALT-DSing×Whisper': ['MMS', 'ALT-DSing', 'Whisper'],
              'MMS×ALT-DSing×ALT-DALI×Whisper': ['MMS', 'ALT-DSing', 'ALT-DALI', 'Whisper'],
              'ALT-DSing×MMS×Whisper (base ALT)': ['ALT-DSing', 'MMS', 'Whisper'],
              'w2v×MMS (base w2v)': ['w2v-960h', 'MMS'],
              'w2v×ALT-DSing (base w2v)': ['w2v-960h', 'ALT-DSing'],
              'w2v×MMS×Whisper (base w2v)': ['w2v-960h', 'MMS', 'Whisper'],
              'w2v×ALT-DSing×MMS (base w2v)': ['w2v-960h', 'ALT-DSing', 'MMS'],
              'w2v×ALT-DSing×MMS×Whisper (base w2v)': ['w2v-960h', 'ALT-DSing', 'MMS', 'Whisper']}
    for name, ms in combos.items():
        if all(m in fix for m in ms):
            if not en:                                # fora do inglês: sem os ALT (o w2v-960h foi bem em pt)
                ms = [m for m in ms if not m.startswith('ALT')]
            r = pick_lrc([fix[m] for m in ms]) if len(ms) > 1 else fix[ms[0]]
            if r:
                v[f'Consenso {name}'] = r
                v[f'Consenso {name} + grade 1/8'] = snap(r, s['_tmap'], 2, 0.06)
    return v

R = {}
for s in songs:
    lang = s.get('_lang', '?')
    for name, ph in variants(s).items():
        m = song_metrics(s['_ref'], ph)
        for grp in ('todas', lang):
            R.setdefault(grp, {}).setdefault(name, []).append(m)

out = {'bias_ms': {m: round(b * 1000) for m, b in bias.items()}}
print('viés mediano (ms):', out['bias_ms'])
for grp in ('todas', 'en', 'pt'):
    if grp not in R:
        continue
    print(f'\n== {grp}')
    print(f"{'variante':44} {'mús':>4} {'palavras':>8} {'med':>5} {'≤100':>5} {'≤250':>5} {'>1s':>5} {'lin.ruins':>9} {'mús>10%':>7}")
    out[grp] = {}
    for name, ms in R[grp].items():
        if not any(ms):
            continue
        r = summarize(ms)
        out[grp][name] = r
        print(f"{name:44} {r['songs']:4} {r['words']:8} {r['median_ms']:5} {r['within_100']:5.3f} {r['within_250']:5.3f} "
              f"{r['over_1s']:5.3f} {r['bad_lines']:9.3f} {r['songs_over1_gt10pct']:7}")
if '--json' in sys.argv:
    json.dump(out, open(sys.argv[sys.argv.index('--json') + 1], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
