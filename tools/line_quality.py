"""Análise por linha no gabarito: erro real de cada linha gerada x sinais disponíveis sem gabarito.

Só imprime números. Saída: taxa de linhas ruins por faixa de cada sinal + melhor regra combinada.
"""
import sys, os, json, difflib, statistics, itertools
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from run import cache_dir
from yl import charts, align

BAD = 0.5  # linha ruim: erro mediano das palavras > 0.5 s
n = lambda s: align.norm_word(s, 'pt')

def line_features(ph, delay):
    rows = []
    for k, p in enumerate(ph):
        ws = p['words']
        first, last_end = ws[0]['t'], max((w.get('end') or w['t']) for w in ws)
        dur = max(0.05, last_end - first)
        nxt = ph[k + 1]['lrc_t'] if k + 1 < len(ph) and ph[k + 1].get('lrc_t') is not None else None
        lrc = p.get('lrc_t')
        lrc_dur = min(8.0, nxt - lrc) if (lrc is not None and nxt is not None and nxt > lrc) else None
        prev_end = max((w.get('end') or w['t']) for w in ph[k - 1]['words']) if k else None
        sc = [w['score'] for w in ws if w.get('score') is not None]
        chars = sum(len(n(w['text'])) for w in ws)
        rows.append({
            'dev': abs(first + delay - lrc) if lrc is not None else None,
            'sdev': (first + delay - lrc) if lrc is not None else None,
            'gap_prev': (first - prev_end) if prev_end is not None else None,
            'ratio': (dur / lrc_dur) if lrc_dur else None,
            'score': statistics.mean(sc) if sc else None,
            'min_score': min(sc) if sc else None,
            'cps': chars / dur,
            'nw': len(ws),
        })
    return rows

def line_errors(ref, ph):
    pred, owner = [], []
    for k, p in enumerate(ph):
        for w in p['words']:
            if n(w['text']):
                pred.append(w); owner.append(k)
    refw = [w for w in ref if n(w['text'])]
    sm = difflib.SequenceMatcher(None, [n(w['text']) for w in refw], [n(w['text']) for w in pred], autojunk=False)
    err = {}
    for b in sm.get_matching_blocks():
        if b.size >= 3:
            for m in range(b.size):
                err.setdefault(owner[b.b + m], []).append(abs(pred[b.b + m]['t'] - refw[b.a + m]['t']))
    return {k: statistics.median(v) for k, v in err.items() if len(v) >= 2}

L = []
folders = json.load(open(os.path.join(ROOT, 'gold_all.json'), encoding='utf-8-sig'))
for f in folders:
    try:
        ap = os.path.join(cache_dir(f), 'aligned.json')
        if not os.path.exists(ap):
            continue
        ph = json.load(open(ap, encoding='utf-8'))
        ch = charts.open_chart(f)
        ref = charts.lyric_events_to_words(ch.read_lyrics()[0], ch.tmap)
        delay = charts.audio_delay(f, ch)
        feats, errs = line_features(ph, delay), line_errors(ref, ph)
        for k, e in errs.items():
            L.append(dict(feats[k], err=e, bad=e > BAD, song=os.path.basename(f)))
    except Exception as ex:
        print('pulou', os.path.basename(f)[:40], type(ex).__name__, ex)
nb = sum(r['bad'] for r in L)
print(f'{len(L)} linhas avaliadas em {len(set(r["song"] for r in L))} músicas; {nb} ruins ({nb/len(L):.0%})\n')

def bins(key, edges):
    out = []
    for lo, hi in zip(edges, edges[1:]):
        sel = [r for r in L if r[key] is not None and lo <= r[key] < hi]
        if sel:
            out.append(f'[{lo:g},{hi:g}) n={len(sel):4} ruins={sum(r["bad"] for r in sel)/len(sel):4.0%}')
    print(f'{key:9}', ' | '.join(out))

bins('dev', [0, .25, .5, 1, 2, 4, 99])
bins('gap_prev', [-99, 0.05, 0.15, 0.4, 1, 3, 99])
bins('ratio', [0, .3, .5, .7, 1, 1.5, 99])
bins('score', [0, .03, .06, .1, .2, .4, 1.1])
bins('min_score', [0, .005, .01, .03, .1, 1.1])
bins('cps', [0, 4, 8, 12, 18, 30, 999])
bins('nw', [1, 2, 4, 7, 12, 99])

# regra combinada: suspeita se dev>a OU ratio<b OU score<c OU (gap_prev<d E dev>e)
best = None
for a, b, c, d, e in itertools.product([0.5, 0.75, 1, 1.5, 99], [0, .3, .4, .5], [0, .03, .05, .08], [-99, .05, .1], [0, .3, .5]):
    def sus(r):
        return ((r['dev'] or 0) > a or (r['ratio'] is not None and r['ratio'] < b) or (r['score'] or 0) < c
                or ((r['gap_prev'] if r['gap_prev'] is not None else 9) < d and (r['dev'] or 0) > e))
    tp = sum(r['bad'] and sus(r) for r in L); fp = sum((not r['bad']) and sus(r) for r in L)
    rec, prec = tp / max(1, nb), tp / max(1, tp + fp)
    f2 = 5 * prec * rec / max(1e-9, 4 * prec + rec)      # F2: recall pesa mais (achar as ruins)
    if best is None or f2 > best[0]:
        best = (f2, a, b, c, d, e, rec, prec, tp + fp)
f2, a, b, c, d, e, rec, prec, flagged = best
print(f'\nmelhor regra: dev>{a} ou ratio<{b} ou score<{c} ou (gap_prev<{d} e dev>{e})')
print(f'  marca {flagged} linhas ({flagged/len(L):.0%}); pega {rec:.0%} das ruins; {prec:.0%} das marcadas são ruins')
json.dump({'dev': a, 'ratio': b, 'score': c, 'gap': d, 'gap_dev': e}, open(os.path.join(ROOT, 'reports', 'line_rule.json'), 'w'))


# ---------------------------------------------------------------- regras explícitas em dois níveis
def level(r):
    dev, ratio, score, cps, gap = r['dev'] or 0, r['ratio'], r['score'] or 0, r['cps'], r['gap_prev']
    glued = gap is not None and gap < 0.05 and (r['sdev'] or 0) < -0.5
    if dev > 2 or (ratio is not None and ratio > 1.5) or cps > 30 or glued or (score < 0.03 and ratio is not None and ratio < 0.5):
        return 2
    if score < 0.03 or (ratio is not None and ratio < 0.3) or cps < 4 or cps > 18 or (gap is not None and gap < 0.05 and score < 0.06):
        return 1
    return 0
for lv, name in ((2, 'alta'), (1, 'média')):
    sel = [r for r in L if level(r) == lv]
    print(f'suspeita {name}: {len(sel)} linhas ({len(sel)/len(L):.0%}); {sum(r["bad"] for r in sel)/max(1,len(sel)):.0%} ruins; '
          f'pega {sum(r["bad"] for r in sel)/nb:.0%} das ruins')
ok = [r for r in L if level(r) == 0]
print(f'sem suspeita: {len(ok)} linhas; {sum(r["bad"] for r in ok)/max(1,len(ok)):.0%} ruins')

# ---------------------------------------------------------------- nível da música
from collections import defaultdict
S = defaultdict(list)
for r in L:
    S[r['song']].append(r)
rows = []
for s, rs in S.items():
    real = sum(r['bad'] for r in rs) / len(rs)
    hi = sum(level(r) == 2 for r in rs) / len(rs)
    any_ = sum(level(r) >= 1 for r in rs) / len(rs)
    rows.append((real, hi, any_, s))
rows.sort()
print('\nmúsica: % linhas ruins (real) x % suspeita alta x % qualquer suspeita')
for real, hi, any_, s in rows:
    print(f'  {real:4.0%}  {hi:4.0%}  {any_:4.0%}  {s[:40]}')
for thr_hi in (0.08, 0.12, 0.15, 0.18, 0.22, 0.26):
    flag = [x for x in rows if x[1] > thr_hi]
    miss = [x for x in rows if x[0] > 0.15 and x[1] <= thr_hi]
    fp = [x for x in flag if x[0] <= 0.10]
    miss30 = [x for x in rows if x[0] > 0.30 and x[1] <= thr_hi]
    print(f'REVISAR se alta>{thr_hi:.0%}: marca {len(flag)}/{len(rows)}; ruins >15% não pegas={len(miss)}; ruins >30% não pegas={len(miss30)}; alarmes falsos (<=10%)={len(fp)}')


# ---------------------------------------------------------------- linha "grudada" na anterior e adiantada
print()
for g, sd in ((0.05, -0.3), (0.05, -0.5), (0.05, -0.8), (0.1, -0.5)):
    sel = [r for r in L if r['gap_prev'] is not None and r['sdev'] is not None and r['gap_prev'] < g and r['sdev'] < sd]
    print(f'grudada (folga<{g}) e adiantada (<{sd} s): n={len(sel)} ruins={sum(r["bad"] for r in sel)/max(1,len(sel)):.0%}')
sel = [r for r in L if r['gap_prev'] is not None and r['gap_prev'] < 0.05 and (r['sdev'] or 0) >= -0.3]
print(f'grudada mas no tempo do LRC: n={len(sel)} ruins={sum(r["bad"] for r in sel)/max(1,len(sel)):.0%}')
