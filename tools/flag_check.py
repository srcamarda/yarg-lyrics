"""Calibração das suspeitas (flag por linha) e do veredito por configuração salva. Só números.

Uso: python tools/flag_check.py <lista.json> <tag> [<tag2 alternativo p/ músicas sem tag> ...]
Para cada nível de flag: quantas linhas, % ruins (erro mediano > 0,5 s); cobertura das ruins pelo nível 2 e pelo nível >=1.
Veredito: músicas com >10% das palavras >1 s (ruins de verdade) x marcadas REVISAR.
"""
import sys, os, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from run import cache_dir
from yl import charts, align
from exp_eval import song_metrics

lst, tags = sys.argv[1], sys.argv[2:]
lv = {0: [0, 0], 1: [0, 0], 2: [0, 0]}
songs = []
for f in json.load(open(lst, encoding='utf-8-sig')):
    cd = cache_dir(f)
    p = next((os.path.join(cd, f'aligned_eval_{t}.json') for t in tags if os.path.exists(os.path.join(cd, f'aligned_eval_{t}.json'))), None)
    if not p:
        continue
    d = json.load(open(p, encoding='utf-8'))
    ph = d['phrases']
    ch = charts.open_chart(f)
    ref = charts.lyric_events_to_words(ch.read_lyrics()[0], ch.tmap)
    m = song_metrics(ref, ph)
    if not m:
        continue
    fl = align.line_flags(ph, d['delay'])                 # recalcula com os limiares ATUAIS do código
    for k, e in m['line_err'].items():
        lv[fl[k]][0] += 1; lv[fl[k]][1] += e > 0.5
    q = align.quality(ph, d['delay'])
    rep = {'quality': q}
    bad_song = sum(e > 1 for e in m['errs']) / len(m['errs']) > 0.10
    songs.append((bad_song, align.verdict(rep) == 'REVISAR', q.get('suspect_hi_frac', 0)))
tot = sum(v[0] for v in lv.values()); bad = sum(v[1] for v in lv.values())
print(f'{tot} linhas, {bad} ruins ({bad / max(1, tot):.1%})')
for k in (0, 1, 2):
    n, b = lv[k]
    print(f'  nível {k}: {n:5} linhas ({n / max(1, tot):5.1%})  ruins entre elas {b / max(1, n):5.1%}  cobre {b / max(1, bad):5.1%} das ruins')
print(f'  nível >=1 cobre {(lv[1][1] + lv[2][1]) / max(1, bad):.1%} das ruins; marca {(lv[1][0] + lv[2][0]) / max(1, tot):.1%} das linhas')
tp = sum(b and r for b, r, _ in songs); fp = sum(r and not b for b, r, _ in songs); fn = sum(b and not r for b, r, _ in songs)
print(f'veredito: {len(songs)} músicas, {sum(b for b, _, _ in songs)} ruins de verdade, {sum(r for _, r, _ in songs)} REVISAR '
      f'| ruins pegas {tp}, ruins deixadas como ok {fn}, boas mandadas revisar {fp}')
