"""Procura regras de suspeita (nível 2) para o padrão novo. Só números.

Sinais por linha: desvio do LRCLIB (dev), razão de duração (ratio), chars/s, folga p/ linha anterior (gap), score,
e DISCORDÂNCIA entre os dois aligners (dis = |início w2v - início ALT-DSing|, só inglês).
Uso: python tools/flag_fit.py   (gabarito; tags do padrão e dos modelos isolados)
"""
import sys, os, json, statistics, itertools
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from run import cache_dir
from yl import charts, align
from exp_eval import song_metrics

B = 'mix_vocals_mel_band_roformer'
n = lambda s: align.norm_word(s, 'pt')

def feats(ph, delay):
    rows = []
    for k, p in enumerate(ph):
        ws = p['words']
        first, last_end = ws[0]['t'], max((w.get('end') or w['t']) for w in ws)
        dur = max(0.05, last_end - first)
        lrc = p.get('lrc_t')
        nxt = ph[k + 1].get('lrc_t') if k + 1 < len(ph) else None
        lrc_dur = min(8.0, nxt - lrc) if (lrc is not None and nxt is not None and nxt > lrc) else None
        prev_end = max((w.get('end') or w['t']) for w in ph[k - 1]['words']) if k else None
        sc = [w['score'] for w in ws if w.get('score') is not None]
        rows.append({'dev': abs(first + delay - lrc) if lrc is not None else 0.0,
                     'ratio': dur / lrc_dur if lrc_dur else 1.0,
                     'cps': sum(len(n(w['text'])) for w in ws) / dur,
                     'gap': first - prev_end if prev_end is not None else 9.0,
                     'score': statistics.mean(sc) if sc else 0.0})
    return rows

L = []
SONG_BAD = {}
for f in json.load(open(os.path.join(ROOT, 'gold_all.json'), encoding='utf-8-sig')):
    cd = cache_dir(f)
    pd = next((os.path.join(cd, f'aligned_eval_{B}_w2v960h_{t}.json') for t in ('2altdsing', 'padrao')
               if os.path.exists(os.path.join(cd, f'aligned_eval_{B}_w2v960h_{t}.json'))), None)
    if not pd:
        continue
    d = json.load(open(pd, encoding='utf-8'))
    ph = d['phrases']
    ch = charts.open_chart(f)
    m = song_metrics(charts.lyric_events_to_words(ch.read_lyrics()[0], ch.tmap), ph)
    if not m:
        continue
    pa, pb = os.path.join(cd, f'aligned_eval_{B}_w2v960h.json'), os.path.join(cd, f'aligned_eval_{B}_altdsing.json')
    dis = None
    if d['lang'] == 'en' and os.path.exists(pa) and os.path.exists(pb):
        a, b = json.load(open(pa, encoding='utf-8'))['phrases'], json.load(open(pb, encoding='utf-8'))['phrases']
        if len(a) == len(b) == len(ph):
            dis = [abs(x['words'][0]['t'] - y['words'][0]['t']) for x, y in zip(a, b)]
    F = feats(ph, d['delay'])
    SONG_BAD[f] = sum(e > 1 for e in m['errs']) / len(m['errs']) > 0.10
    for k, e in m['line_err'].items():
        L.append(dict(F[k], dis=dis[k] if dis else None, bad=e > 0.5, lang=d['lang'], song=f))

nb = sum(r['bad'] for r in L)
print(f'{len(L)} linhas, {nb} ruins ({nb / len(L):.1%}); com sinal de discordância: {sum(r["dis"] is not None for r in L)}')
print('\ntaxa de ruins por faixa de cada sinal:')
BINS = {'dev': (0.3, 0.6, 1, 2), 'ratio': (0.3, 0.5, 1.5, 2), 'cps': (4, 8, 18, 30), 'gap': (0.02, 0.05, 0.2),
        'score': (0.02, 0.05, 0.1, 0.2), 'dis': (0.1, 0.25, 0.5, 1)}
for s, cuts in BINS.items():
    vals = [r for r in L if r[s] is not None]
    edges = (-1e9,) + cuts + (1e9,)
    parts = []
    for lo, hi in zip(edges, edges[1:]):
        g = [r for r in vals if lo <= r[s] < hi]
        if g:
            parts.append(f"[{lo if lo > -1e8 else '-'}–{hi if hi < 1e8 else '+'}) n={len(g)} ruins={sum(r['bad'] for r in g) / len(g):.0%}")
    print(f'  {s:6} ' + '  '.join(parts))

def ev(rule):
    fl = [r for r in L if rule(r)]
    tp = sum(r['bad'] for r in fl)
    return len(fl), tp / max(1, len(fl)), tp / max(1, nb)

print('\nregras candidatas p/ nível 2 (marcadas, precisão, cobertura):')
cands = {}
for dv, dis_t, rt, sc in itertools.product((1, 1.5, 2, 3), (0.3, 0.5, 0.8, None), (1.5, 2, None), (0.02, 0.05, None)):
    def rule(r, dv=dv, dis_t=dis_t, rt=rt, sc=sc):
        return (r['dev'] > dv or (dis_t is not None and r['dis'] is not None and r['dis'] > dis_t)
                or (rt is not None and r['ratio'] > rt) or (sc is not None and r['score'] < sc))
    nf, p, c = ev(rule)
    cands[(dv, dis_t, rt, sc)] = (nf, p, c)
best = sorted(cands.items(), key=lambda kv: -(2 * kv[1][1] * kv[1][2] / max(1e-9, kv[1][1] + kv[1][2])))[:12]
for (dv, dis_t, rt, sc), (nf, p, c) in best:
    print(f'  dev>{dv} | dis>{dis_t} | ratio>{rt} | score<{sc}:  {nf:4} linhas ({nf / len(L):5.1%})  precisão {p:.2f}  cobertura {c:.2f}')
nf, p, c = ev(lambda r: r['dev'] > 2 or r['ratio'] > 1.5 or r['cps'] > 30 or (r['score'] < 0.03 and r['ratio'] < 0.5))
print(f'  regra atual (aprox.):  {nf} linhas  precisão {p:.2f}  cobertura {c:.2f}')

# ---------------------------------------------------------------- regra proposta + veredito por música
L2 = lambda r: (r['dis'] is not None and r['dis'] > 0.8) or r['dev'] > 3 or r['ratio'] > 1.5 or r['cps'] > 30 or r['gap'] < 0.02
L1 = lambda r: not L2(r) and (r['score'] < 0.05 or (r['dis'] is not None and r['dis'] > 0.3) or r['dev'] > 2 or r['cps'] < 4)
for name, rule in (('proposta nível 2', L2), ('proposta nível 1', L1), ('proposta nível >=1', lambda r: L1(r) or L2(r))):
    nf, p, c = ev(rule)
    print(f'{name:20} {nf:4} linhas ({nf / len(L):5.1%})  precisão {p:.2f}  cobertura {c:.2f}')
nf0 = [r for r in L if not (L1(r) or L2(r))]
print(f'sem flag: {len(nf0)} linhas, ruins entre elas {sum(r["bad"] for r in nf0) / len(nf0):.1%}')

print('\nveredito por música (ruim = >10% das palavras com erro >1 s):', sum(SONG_BAD.values()), 'de', len(SONG_BAD))
per = {}
for r in L:
    per.setdefault(r['song'], []).append(r)
for t in (0.04, 0.06, 0.08, 0.10, 0.12, 0.15):
    rev = {s for s, rs in per.items() if sum(L2(r) for r in rs) / len(rs) > t}
    tp = sum(SONG_BAD[s] for s in rev); fn = sum(SONG_BAD[s] for s in per if s not in rev)
    print(f'  REVISAR se nível2 > {t:.2f}: {len(rev):2} músicas | ruins pegas {tp}, ruins como ok {fn}, boas p/ revisar {len(rev) - tp}')
