"""Varre a biblioteca, agrupa versões pelo nome e compara o áudio de cada par. Grava reports/twins.json.

Uso: python tools\\find_twins.py "<raiz da biblioteca>"
Imprime só nomes de músicas e números.
"""
import sys, os, json, itertools, collections, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from run import cache_dir
from yl import batch, twins, charts

lib = sys.argv[1]
groups = collections.defaultdict(list)
for f in batch.find_songs(lib):
    try:
        groups[twins.key(f)].append(f)
    except Exception:
        pass
groups = {k: v for k, v in groups.items() if len(v) > 1}
print(f'{len(groups)} grupos com 2+ versões', flush=True)

def lyr_kind(f):
    try:
        if charts.open_chart(f).has_lyrics():
            return 'oficial'
    except Exception:
        return '?'
    if batch.generated(f) or any(n.lower().endswith('.bak') for n in os.listdir(f)):
        return 'gerada'
    return 'sem'

out, t0 = [], time.time()
for k, fs in sorted(groups.items()):
    fps = {}
    for f in fs:
        try:
            fps[f] = twins.fingerprint(f, cache_dir(f))
        except Exception as e:
            fps[f] = None
    for a, b in itertools.combinations(fs, 2):
        if fps[a] is None or fps[b] is None:
            continue
        c = twins.compare(fps[a], fps[b])
        v = twins.verdict(c)
        rec = {'a': a, 'b': b, 'verdict': v, **c, 'lyr_a': lyr_kind(a), 'lyr_b': lyr_kind(b)}
        out.append(rec)
        name = lambda p: f"{os.path.basename(os.path.dirname(p))[:14]}/{os.path.basename(p)[:34]}"
        print(f"{v:9} off={c['offset_s']:+7.2f}s janelas={c['match_frac']:4.0%} ({c['windows']:2}) | "
              f"{name(a)} [{rec['lyr_a']}]  ×  {name(b)} [{rec['lyr_b']}]", flush=True)
json.dump(out, open(os.path.join(ROOT, 'reports', 'twins.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
cnt = collections.Counter(r['verdict'] for r in out)
useful = [r for r in out if r['verdict'] == 'igual' and {r['lyr_a'], r['lyr_b']} & {'oficial', 'gerada'} and 'sem' in (r['lyr_a'], r['lyr_b'])]
print(f'\n{len(out)} pares: {dict(cnt)} | iguais em que um lado tem letra e o outro não: {len(useful)} | {time.time()-t0:.0f}s')
