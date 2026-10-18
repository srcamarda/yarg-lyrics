"""Reaplica align.verdict aos relatórios de avaliação e mostra erro real x veredito (só números)."""
import sys, os, json, glob
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from yl import align
rows = {}
for p in sorted(glob.glob(os.path.join(ROOT, 'reports', '*-eval.jsonl'))):
    for r in map(json.loads, open(p, encoding='utf-8')):
        if r.get('eval', {}).get('matched'):
            rows[r['folder']] = r
print('VERDICT', align.VERDICT)
for r in sorted(rows.values(), key=lambda r: r['eval']['over_1s']):
    print(f"{r['eval']['over_1s']:5.2f} {align.verdict(r):8} {r['lang']} {(r['artist'] + ' - ' + r['title'])[:40]}")
