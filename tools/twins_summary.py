"""Resumo do reports/twins.json: pares com o mesmo áudio em que dá para copiar letra. Só nomes e números."""
import json, os, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = json.load(open(os.path.join(ROOT, 'reports', 'twins.json'), encoding='utf-8'))
nm = lambda p: f"{os.path.basename(os.path.dirname(p))[:22]} / {os.path.basename(p)[:44]}"
same = [t for t in T if t['verdict'] == 'igual']
by = collections.Counter()
for t in same:
    a, b = t['lyr_a'], t['lyr_b']
    if 'oficial' in (a, b) and 'sem' in (a, b): by['oficial → sem letra'] += 1
    elif 'gerada' in (a, b) and 'sem' in (a, b): by['gerada → sem letra'] += 1
    elif a == b == 'sem': by['as duas sem letra (gerar uma e copiar)'] += 1
    elif a == b == 'gerada': by['as duas geradas (copiar a revisada)'] += 1
    elif 'oficial' in (a, b) and 'gerada' in (a, b): by['oficial × gerada (trocar pela oficial)'] += 1
    else: by[f'{a} × {b}'] += 1
print('pares com o mesmo áudio:', len(same))
for k, v in by.most_common():
    print(f'  {v:3}  {k}')
print('\noficial disponível para música sem letra (ou com letra gerada):')
for t in same:
    if 'oficial' in (t['lyr_a'], t['lyr_b']) and {'sem', 'gerada'} & {t['lyr_a'], t['lyr_b']}:
        src, dst = (t['a'], t['b']) if t['lyr_a'] == 'oficial' else (t['b'], t['a'])
        print(f"  {nm(dst)}  ⇐  {nm(src)}  (defasagem {t['offset_s']:+.2f} s, {t['match_frac']:.0%})")
print('\nparecidos (não copia automaticamente):')
for t in T:
    if t['verdict'] == 'parecido':
        print(f"  {nm(t['a'])}  ×  {nm(t['b'])}  ({t['match_frac']:.0%}, {t['offset_s']:+.1f} s)")
