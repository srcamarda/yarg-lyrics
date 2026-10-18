"""Reavalia aligned.json do cache contra a letra existente, só com blocos >=3 palavras. Imprime só métricas."""
import sys, os, json, glob, difflib, statistics
sys.path.insert(0, os.path.dirname(__file__))
from yl import charts, align
n = lambda s: align.norm_word(s, 'pt')
for folder in sys.argv[1:]:
    ch = charts.open_chart(folder)
    ref = [w for w in charts.lyric_events_to_words(ch.read_lyrics()[0], ch.tmap) if n(w['text'])]
    key = os.path.basename(folder)[:20].replace('[', '_').replace(']', '_')
    cd = [d for d in glob.glob(os.path.join(os.path.dirname(__file__), 'cache', '*')) if os.path.basename(d).startswith(key)][0]
    ph = json.load(open(os.path.join(cd, 'aligned.json'), encoding='utf-8'))
    pred = [w for p in ph for w in p['words'] if n(w['text'])]
    sm = difflib.SequenceMatcher(None, [n(w['text']) for w in ref], [n(w['text']) for w in pred], autojunk=False)
    errs = []
    for b in sm.get_matching_blocks():
        if b.size >= 3:
            errs += [pred[b.b + k]['t'] - ref[b.a + k]['t'] for k in range(b.size)]
    ab = sorted(abs(e) for e in errs)
    big = sum(a > 1 for a in ab)
    print(f"{os.path.basename(folder)[:32]:32} matched {len(ab):3}/{len(ref):3} med={statistics.median(ab)*1000:5.0f}ms "
          f"p90={ab[int(.9*(len(ab)-1))]*1000:6.0f}ms <100={sum(a<=.1 for a in ab)/len(ab):.2f} "
          f"<250={sum(a<=.25 for a in ab)/len(ab):.2f} >1s={big/len(ab):.2f}")
