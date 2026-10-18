"""Lê reports/*-eval.jsonl e mostra, por música, sinais de confiança x erro real. Só números."""
import json, glob, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = {}
for p in sorted(glob.glob(os.path.join(ROOT, 'reports', '*-eval.jsonl'))):
    for line in open(p, encoding='utf-8'):
        r = json.loads(line)
        if 'eval' in r and r['eval'].get('matched'):
            rows[r['folder']] = r  # mais recente vence
print(f"{'musica':34} {'lg':2} {'voc':6} {'bad':>5} {'mls':>5} {'mean':>5} {'lrcD':>5} {'dis':>5} {'fix':>4} | {'<100':>5} {'>1s':>5} {'cov':>5} {'med':>6}  verdict")
for r in sorted(rows.values(), key=lambda r: r['eval']['over_1s']):
    q, e = r['quality'], r['eval']
    print(f"{(r['artist']+' - '+r['title'])[:34]:34} {r['lang']:2} {r['vocals']:6} {q.get('bad_line_frac',0):5.2f} "
          f"{q.get('median_line_score',0):5.2f} {q['mean_score']:5.2f} {r.get('lrclib',{}).get('duration_delta_s',0):5.1f} {q.get('lrc_disagree_frac',0):5.2f} {r.get('lines_realigned',0):4} | "
          f"{e['within_100ms']:5.2f} {e['over_1s']:5.2f} {e['coverage']:5.2f} {e['median_ms']:6}  {r['status']}")
