import sys, os, json, glob, difflib
sys.path.insert(0, os.path.dirname(__file__))
from yl import charts, lyrics, align
folder = sys.argv[1]
ch = charts.open_chart(folder)
ref = charts.lyric_events_to_words(ch.read_lyrics()[0], ch.tmap)
cd = [d for d in glob.glob(os.path.join(os.path.dirname(__file__), 'cache', '*'))
      if os.path.basename(d).startswith(os.path.basename(folder)[:20].replace('[', '_').replace(']', '_'))][0]
rec = json.load(open(os.path.join(cd, 'lrclib.json'), encoding='utf-8'))
lines, _ = lyrics.from_record(rec)
n = lambda s: align.norm_word(s, 'pt')
rw = [n(w['text']) for w in ref if n(w['text'])]
lw = [n(w) for l in lines for w in l['words'] if n(w)]
print('ref words', len(rw), 'span', round(ref[0]['t'], 1), '-', round(ref[-1]['t'], 1))
print('lrc words', len(lw), 'lines', len(lines), 'span', lines[0]['t'], '-', lines[-1]['t'])
print('vocab overlap ref->lrc', round(len(set(rw) & set(lw)) / len(set(rw)), 2))
sm = difflib.SequenceMatcher(None, rw, lw, autojunk=False)
print('seq ratio', round(sm.ratio(), 2), 'matched', sum(b.size for b in sm.get_matching_blocks()))
# onde caem os inícios de frase de referência vs linhas LRC (só tempos)
_, phr = ch.read_lyrics()
ps = [round(ch.tmap.t2s(a), 1) for a, b in phr]
print('ref phrase starts', ps[:40])
print('lrc line starts  ', [round(l['t'], 1) for l in lines][:40])
