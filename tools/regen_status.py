"""Andamento/resultado de uma regeneração pela UI: tempo, voz, 2ª opinião e status por música. Só números e títulos.
Uso: python tools/regen_status.py lista.json [--antes]   (--antes: compara com o último status anterior a 20/10)"""
import sys, os, json, glob
from collections import Counter
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
s = json.load(open(os.path.join(ROOT, 'ui_state.json'), encoding='utf-8'))
lst = json.load(open(sys.argv[1], encoding='utf-8'))
key = lambda f: os.path.normcase(os.path.abspath(f))
old = {}
if '--antes' in sys.argv:
    for p in sorted(glob.glob(os.path.join(ROOT, 'reports', '2026*.jsonl'))):
        b = os.path.basename(p)
        if '-eval' in b or b >= '20261020':
            continue
        for r in map(json.loads, open(p, encoding='utf-8')):
            if r.get('folder') and 'status' in r and not str(r['status']).startswith('skip'):
                old[key(r['folder'])] = r['status']
new = Counter(); trans = Counter(); secs = []
for f in lst:
    r = (s.get(key(f), {}).get('report') or {})
    if not r.get('aligner'):
        continue
    st = str(r.get('status')).split(' (')[0].split(':')[0]
    new[st] += 1
    secs.append(r.get('seconds') or 0)
    if '--antes' in sys.argv:
        trans[(str(old.get(key(f), '?')).split(' (')[0].split(':')[0], st)] += 1
    else:
        print(f"{r.get('seconds'):6}s voz={r.get('vocals')} 2a={r.get('second_opinion')} {st:10} {os.path.basename(f)[:40]}")
print('feitas:', len(secs), dict(new), f'mediana {sorted(secs)[len(secs) // 2] if secs else 0}s')
for (a, b), v in sorted(trans.items(), key=lambda kv: -kv[1]):
    print(f'  {a:12} -> {b:12} {v}')
