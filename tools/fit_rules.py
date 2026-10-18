"""Compara regras candidatas de veredito no gabarito. Só contagens e títulos."""
import json, glob, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = {}
for p in sorted(glob.glob(os.path.join(ROOT, 'reports', '*-eval.jsonl'))):
    for r in map(json.loads, open(p, encoding='utf-8')):
        if r.get('eval', {}).get('matched') and 'vocal_rms_frac' in r.get('quality', {}):
            rows[r['folder']] = r
R = list(rows.values())
f = lambda r: (r['quality'].get('lrc_disagree_frac', 0), r['quality']['mean_score'], (r.get('lrclib') or {}).get('duration_delta_s', 0))
RULES = {
    'atual':   lambda d, m, l: d > 0.4 or m < 0.10 or l > 8,
    'R2':      lambda d, m, l: d > 0.4 or m < 0.085 or (l > 8 and (d > 0.25 or m < 0.12)),
    'R3':      lambda d, m, l: d > 0.35 or m < 0.075 or (l > 8 and (d > 0.25 or m < 0.12)),
}
for bad_thr in (0.15, 0.30):
    nbad = sum(r['eval']['over_1s'] > bad_thr for r in R)
    print(f'\n-- ruim = >{bad_thr:.0%} das palavras com erro >1s ({nbad} de {len(R)})')
    for name, rule in RULES.items():
        flag = [r for r in R if rule(*f(r))]
        miss = [r['title'] for r in R if r['eval']['over_1s'] > bad_thr and r not in flag]
        fp = [r['title'] for r in flag if r['eval']['over_1s'] <= bad_thr]
        print(f"{name:6} REVISAR={len(flag):2}  ruins não pegas={len(miss)} {miss}  alarmes falsos={len(fp)}")
        if bad_thr == 0.30:
            print('        falsos:', fp)
inst = lambda q: q['vocal_rms_frac'] < 0.30 or (q['chars_per_s'] < 0.5 and q['voiced_win_frac'] < 0.15)
print('\ncom voz tomadas por instrumental (rms<0.30 ou cps<0.5&vwin<0.15):', [r['title'] for r in R if inst(r['quality'])])
print('menor rms/cps entre músicas com voz:', min(r['quality']['vocal_rms_frac'] for r in R), min(r['quality']['chars_per_s'] for r in R))
