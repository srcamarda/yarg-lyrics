"""Tabela de métricas para configurações salvas (aligned_eval_<tag>.json), por idioma. Só números.

Uso: python tools/exp_tags.py <lista.json> <tag> [<tag> ...]
     (tag 'X' lê aligned_eval_X.json; compara só músicas que têm todas as tags)
"""
import sys, os, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from run import cache_dir
from yl import charts
from exp_eval import song_metrics, summarize

lst, tags = sys.argv[1], sys.argv[2:]
R = {}
missing = 0
for f in json.load(open(lst, encoding='utf-8-sig')):
    cd = cache_dir(f)
    # 'a|b' = usa a primeira que existir (ex.: padrão em inglês tem _2altdsing, em português _padrao)
    ps = [next((os.path.join(cd, f'aligned_eval_{x}.json') for x in t.split('|')
                if os.path.exists(os.path.join(cd, f'aligned_eval_{x}.json'))), '') for t in tags]
    if not all(os.path.exists(p) for p in ps):
        missing += 1; continue
    ch = charts.open_chart(f)
    ref = charts.lyric_events_to_words(ch.read_lyrics()[0], ch.tmap)
    for t, p in zip(tags, ps):
        d = json.load(open(p, encoding='utf-8'))
        m = song_metrics(ref, d['phrases'])
        for grp in ('todas', d.get('lang', '?')):
            R.setdefault(grp, {}).setdefault(t, []).append(m)
print(f'(músicas sem todas as configurações: {missing})')
for grp in ('todas', 'en', 'pt'):
    if grp not in R:
        continue
    print(f'== {grp}')
    print(f"{'configuração':48} {'mús':>4} {'palavras':>8} {'med':>5} {'≤100':>5} {'≤250':>5} {'>1s':>5} {'lin.ruins':>9} {'mús>10%':>7}")
    for t, ms in R[grp].items():
        if any(ms):
            r = summarize(ms)
            print(f"{t[:48]:48} {r['songs']:4} {r['words']:8} {r['median_ms']:5} {r['within_100']:5.3f} {r['within_250']:5.3f} "
                  f"{r['over_1s']:5.3f} {r['bad_lines']:9.3f} {r['songs_over1_gt10pct']:7}")
