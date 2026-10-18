"""Copia a letra oficial para versões com o MESMO áudio que estão sem letra (ou com letra gerada).

Usa reports/twins.json (tools/find_twins.py) e a API da interface (precisa do servidor rodando).
Pula destinos com ajustes manuais. Imprime só nomes e números.
"""
import os, json, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = 'http://127.0.0.1:8765'

def call(path, body=None):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'error': json.loads(e.read()).get('detail', str(e))}

T = json.load(open(os.path.join(ROOT, 'reports', 'twins.json'), encoding='utf-8'))
best = {}
for t in T:
    if t['verdict'] != 'igual':
        continue
    kinds = (t['lyr_a'], t['lyr_b'])
    if 'oficial' not in kinds or not ({'sem', 'gerada'} & set(kinds)):
        continue
    src, dst = (t['a'], t['b']) if t['lyr_a'] == 'oficial' else (t['b'], t['a'])
    score = (t['match_frac'], -abs(t['offset_s']))          # prefere a fonte que bate melhor e sem defasagem
    if dst not in best or score > best[dst][0]:
        best[dst] = (score, src)

nm = lambda p: f"{os.path.basename(os.path.dirname(p))[:20]} / {os.path.basename(p)[:44]}"
done = skipped = failed = 0
for dst, (_, src) in sorted(best.items()):
    info = call('/api/song?folder=' + urllib.parse.quote(dst))
    if info.get('edited'):
        print(f'pulada (tem ajustes manuais): {nm(dst)}'); skipped += 1; continue
    r = call('/api/copy-lyrics', {'source': src, 'target': dst})
    if 'error' in r:
        print(f'FALHOU {nm(dst)}: {r["error"]}'); failed += 1
    else:
        print(f'ok  {nm(dst)}  ⇐  {nm(src)}  ({r["phrases"]} linhas, defasagem {r["offset_s"]:+.2f} s)'); done += 1
print(f'\ncopiadas: {done} | puladas: {skipped} | falharam: {failed}')
