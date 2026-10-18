"""Recalcula qualidade/veredito das músicas já geradas a partir do aligned.json (sem realinhar).

Uso: python tools\\requalify.py "<setlist>" [...]
Grava um relatório novo em reports\\ (o mais recente vale na interface) e atualiza ui_state.json.
"""
import sys, os, json, glob, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from run import cache_dir
from yl import charts, batch, align

def last_reports():
    rep = {}
    for p in sorted(glob.glob(os.path.join(ROOT, 'reports', '*.jsonl'))):
        if p.endswith('-eval.jsonl'):
            continue
        for line in open(p, encoding='utf-8'):
            r = json.loads(line)
            if r.get('folder') and not str(r.get('status', '')).startswith('skip'):
                rep[os.path.normcase(os.path.abspath(r['folder']))] = r
    return rep

reps = last_reports()
st_path = os.path.join(ROOT, 'ui_state.json')
state = json.load(open(st_path, encoding='utf-8')) if os.path.exists(st_path) else {}
out_path = os.path.join(ROOT, 'reports', time.strftime('%Y%m%d-%H%M%S') + '-requalify.jsonl')
changed = {'ok->REVISAR': 0, 'REVISAR->ok': 0, 'igual': 0}
for root in sys.argv[1:]:
    for f in batch.find_songs(root):
        key = os.path.normcase(os.path.abspath(f))
        r = (state.get(key) or {}).get('report') or reps.get(key)
        ap = os.path.join(cache_dir(f), 'aligned.json')
        if not r or r.get('status') not in ('ok', 'REVISAR') or not os.path.exists(ap):
            continue
        ph = json.load(open(ap, encoding='utf-8'))
        if not ph or not any(w.get('score') is not None for p in ph for w in p['words']):
            continue                      # ajustado à mão: sem métricas para recalcular
        delay = charts.audio_delay(f, charts.open_chart(f))
        old = r['status']
        q = align.quality(ph, delay)
        r['quality'] = {**r.get('quality', {}), **q}
        r['status'] = align.verdict(r)
        json.dump(ph, open(ap, 'w', encoding='utf-8'), ensure_ascii=False)     # grava as marcas por linha
        with open(out_path, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')
        if key in state and 'report' in state[key]:
            state[key]['report'] = r
        changed['igual' if old == r['status'] else f'{old}->{r["status"]}'] += 1
json.dump(state, open(st_path, 'w', encoding='utf-8'), ensure_ascii=False)
print(changed)
