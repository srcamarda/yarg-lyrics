"""Compara dois relatórios -eval (médias e músicas que mudaram). Só números."""
import sys, json, statistics
def load(p):
    return {r['folder']: r for r in map(json.loads, open(p, encoding='utf-8')) if r.get('eval', {}).get('matched')}
a, b = load(sys.argv[1]), load(sys.argv[2])
common = sorted(set(a) & set(b))
for k in ('within_100ms', 'within_250ms', 'over_1s', 'median_ms'):
    va, vb = [a[f]['eval'][k] for f in common], [b[f]['eval'][k] for f in common]
    print(f'{k:13} antes={statistics.mean(va):7.3f}  depois={statistics.mean(vb):7.3f}')
better = sum(b[f]['eval']['over_1s'] < a[f]['eval']['over_1s'] - 0.02 for f in common)
worse = sum(b[f]['eval']['over_1s'] > a[f]['eval']['over_1s'] + 0.02 for f in common)
print(f'{len(common)} músicas: melhoraram {better}, pioraram {worse} (>1s, margem 2 p.p.)')
for f in common:
    d = b[f]['eval']['over_1s'] - a[f]['eval']['over_1s']
    if abs(d) > 0.05:
        print(f"  {d:+.2f}  reparadas={b[f].get('lines_repaired', 0):2}  {b[f]['title'][:40]}")
