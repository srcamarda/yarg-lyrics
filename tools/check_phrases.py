"""Confere a coerência frase x palavra no aligned.json e no chart gerado (só números)."""
import sys, os, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from run import cache_dir
from yl import charts, batch
folder = sys.argv[1]
ph = json.load(open(os.path.join(cache_dir(folder), 'aligned.json'), encoding='utf-8'))
bad_order = bad_bounds = 0
for i, p in enumerate(ph):
    ws = p['words']
    if i and ws[0]['t'] < ph[i - 1]['words'][-1]['t']:
        bad_order += 1
    if ws[0]['t'] < p['start'] or ws[-1]['t'] > p['end']:
        bad_bounds += 1
print(f'aligned.json: {len(ph)} frases | 1ª palavra antes da última da frase anterior: {bad_order} | palavra fora da própria frase: {bad_bounds}')
for i in range(min(4, len(ph))):
    p = ph[i]
    print(f"  frase {i}: start={p['start']:.2f} end={p['end']:.2f} palavras {p['words'][0]['t']:.2f}..{p['words'][-1]['t']:.2f} (n={len(p['words'])})")
g = batch.generated(folder) or charts.open_chart(folder, prefer_backup=False).path
ch = charts.Chart(g) if g.lower().endswith('.chart') else charts.Midi(g)
lyr, phr = ch.read_lyrics()
print(f'arquivo: {os.path.basename(g)} | {len(phr)} frases lidas, {len(lyr)} palavras')
for i in range(min(4, len(phr))):
    a, b = phr[i]
    inside = sum(a <= t <= b for t, _ in lyr)
    print(f'  frase {i}: {ch.tmap.t2s(a):.2f}..{ch.tmap.t2s(b):.2f}  palavras dentro: {inside}')
