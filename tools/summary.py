"""Resumo de uma setlist a partir de reports/*.jsonl (não-eval). Só metadados, nunca letra."""
import sys, os, json, glob, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root = os.path.abspath(sys.argv[1]).lower()
rows = {}
for p in sorted(glob.glob(os.path.join(ROOT, 'reports', '*.jsonl'))):
    if p.endswith('-eval.jsonl'):
        continue
    for r in map(json.loads, open(p, encoding='utf-8')):
        f = r.get('folder', '')
        if os.path.abspath(f).lower().startswith(root) and not str(r.get('status', '')).startswith('skip: já gerado'):
            rows[os.path.abspath(f).lower()] = r
cnt = collections.Counter(str(r.get('status')).split(':')[0] for r in rows.values())
print('total', len(rows), dict(cnt))
for kind in ('erro', 'REVISAR', 'sem letra'):
    sel = [r for r in rows.values() if str(r.get('status')).startswith(kind)]
    if not sel:
        continue
    print(f'\n== {kind} ({len(sel)})')
    for r in sorted(sel, key=lambda r: os.path.basename(r['folder'])):
        q = r.get('quality', {})
        why = []
        if (r.get('lrclib') or {}).get('duration_delta_s', 0) > 8: why.append(f"duração LRCLIB Δ{r['lrclib']['duration_delta_s']}s")
        if q.get('lrc_disagree_frac', 0) > 0.4: why.append(f"desencontro LRC {q['lrc_disagree_frac']:.0%}")
        if q and q.get('mean_score', 1) < 0.10: why.append(f"confiança {q['mean_score']:.2f}")
        name = (r.get('artist') or '') + ' - ' + (r.get('title') or os.path.basename(r['folder']))
        extra = r['status'] if kind == 'erro' else '; '.join(why)
        print(f"  {name[:60]:60} {extra}")
