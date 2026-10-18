"""Por linha: índice, âncora LRC (+off), início alinhado, score médio, erro mediano vs referência. Só números."""
import sys, os, json, glob, difflib, statistics
sys.path.insert(0, os.path.dirname(__file__))
from yl import charts, align
n = lambda s: align.norm_word(s, 'pt')
folder = sys.argv[1]
ch = charts.open_chart(folder)
ref = [w for w in charts.lyric_events_to_words(ch.read_lyrics()[0], ch.tmap) if n(w['text'])]
key = os.path.basename(folder)[:20].replace('[', '_').replace(']', '_')
cd = [d for d in glob.glob(os.path.join(os.path.dirname(__file__), 'cache', '*')) if os.path.basename(d).startswith(key)][0]
ph = json.load(open(os.path.join(cd, 'aligned.json'), encoding='utf-8'))
pred, owner = [], []
for i, p in enumerate(ph):
    for w in p['words']:
        if n(w['text']):
            pred.append(w); owner.append(i)
sm = difflib.SequenceMatcher(None, [n(w['text']) for w in ref], [n(w['text']) for w in pred], autojunk=False)
err = {}
for b in sm.get_matching_blocks():
    if b.size >= 3:
        for k in range(b.size):
            err.setdefault(owner[b.b + k], []).append(pred[b.b + k]['t'] - ref[b.a + k]['t'])
print('line  lrc_t  start  dur  nw score   err_s')
for i, p in enumerate(ph):
    sc = [w['score'] for w in p['words'] if w['score'] is not None]
    e = err.get(i)
    print(f"{i:3} {p['lrc_t']:6.1f} {p['start']:6.1f} {p['words'][-1]['end']-p['words'][0]['t']:4.1f} {len(p['words']):3} "
          f"{(sum(sc)/len(sc) if sc else 0):.2f} {('%7.2f' % statistics.median(e)) if e else '     --'}")
