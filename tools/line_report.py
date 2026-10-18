"""Sinais por linha de uma música gerada (só números): índice, marca, desvio do LRC, folga p/ anterior, razão de duração, confiança."""
import sys, os, json, statistics
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from run import cache_dir
from yl import charts, align
f = sys.argv[1]
ph = json.load(open(os.path.join(cache_dir(f), 'aligned.json'), encoding='utf-8'))
delay = charts.audio_delay(f, charts.open_chart(f))
fl = align.line_flags(ph, delay)
print(' i fl   início    dev   gap  ratio  score  nw')
for k, p in enumerate(ph):
    ws = p['words']; first = ws[0]['t']
    end = max((w.get('end') or w['t']) for w in ws)
    lrc = p.get('lrc_t'); nxt = ph[k + 1].get('lrc_t') if k + 1 < len(ph) else None
    dev = (first + delay - lrc) if lrc is not None else float('nan')
    gap = first - max((w.get('end') or w['t']) for w in ph[k - 1]['words']) if k else float('nan')
    ratio = (end - first) / min(8, nxt - lrc) if (lrc is not None and nxt and nxt > lrc) else float('nan')
    sc = [w['score'] for w in ws if w.get('score') is not None]
    print(f"{k:2} {fl[k]:2} {first:8.2f} {dev:+6.2f} {gap:5.2f} {ratio:6.2f} {statistics.mean(sc) if sc else float('nan'):6.3f} {len(ws):3}")
