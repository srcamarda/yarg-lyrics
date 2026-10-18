"""Calibra o veredito ok/REVISAR no gabarito (relatórios -eval com métricas de voz). Só números."""
import json, glob, os, itertools
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = {}
for p in sorted(glob.glob(os.path.join(ROOT, 'reports', '*-eval.jsonl'))):
    for r in map(json.loads, open(p, encoding='utf-8')):
        if r.get('eval', {}).get('matched') and 'vocal_rms_frac' in r.get('quality', {}):
            rows[r['folder']] = r
R = list(rows.values())
BAD = 0.15   # ruim = mais de 15% das palavras com erro > 1 s
bad = lambda r: r['eval']['over_1s'] > BAD
print(f'{len(R)} músicas, {sum(map(bad, R))} ruins (>{BAD:.0%} palavras >1s)\n')
print(f"{'musica':36} lg  mean   mls   bad   dis  lrcD   rms   cps  vwin |  <100   >1s")
for r in sorted(R, key=lambda r: r['eval']['over_1s']):
    q, e = r['quality'], r['eval']
    print(f"{(r['artist']+' - '+r['title'])[:36]:36} {r['lang']} {q['mean_score']:5.2f} {q.get('median_line_score',0):5.2f} "
          f"{q.get('bad_line_frac',0):5.2f} {q.get('lrc_disagree_frac',0):5.2f} {(r.get('lrclib') or {}).get('duration_delta_s',0):5.1f} "
          f"{q['vocal_rms_frac']:5.2f} {q['chars_per_s']:5.2f} {q['voiced_win_frac']:5.2f} | {e['within_100ms']:5.2f} {e['over_1s']:5.2f}")
# busca de regra: REVISAR se dis > a  OU  mean < b  OU  lrcD > c
best = None
for a, b, c in itertools.product([0.3, 0.35, 0.4, 0.5, 0.6, 1.1], [0, 0.03, 0.05, 0.07, 0.1], [8, 12, 20, 1e9]):
    flag = lambda r: (r['quality'].get('lrc_disagree_frac', 0) > a or r['quality']['mean_score'] < b
                      or (r.get('lrclib') or {}).get('duration_delta_s', 0) > c)
    miss = sum(bad(r) and not flag(r) for r in R)
    fp = sum(flag(r) and not bad(r) for r in R)
    key = (miss * 3 + fp, miss, fp)
    if best is None or key < best[0]:
        best = (key, a, b, c)
(score, miss, fp), a, b, c = best
print(f'\nmelhor regra: dis>{a} ou mean<{b} ou lrcD>{c}  -> ruins não pegas={miss}, falsos alarmes={fp}')
cur = lambda r: r['quality'].get('lrc_disagree_frac', 0) > 0.4 or r['quality']['mean_score'] < 0.10 or (r.get('lrclib') or {}).get('duration_delta_s', 0) > 8
print(f"regra atual (dis>0.4 ou mean<0.10 ou lrcD>8): não pegas={sum(bad(r) and not cur(r) for r in R)}, falsos alarmes={sum(cur(r) and not bad(r) for r in R)}")
inst = lambda q: q['vocal_rms_frac'] < 0.35 or (q['chars_per_s'] < 0.5 and q['voiced_win_frac'] < 0.15)
print('músicas COM voz que seriam tomadas por instrumental:', sum(inst(r['quality']) for r in R),
      [r['title'] for r in R if inst(r['quality'])])
