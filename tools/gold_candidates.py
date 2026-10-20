"""Lista músicas da biblioteca com letra OFICIAL (do chart original) que podem entrar no gabarito. Só contagens.

Uso: python tools/gold_candidates.py <raiz da biblioteca> [...]   -> reports/gold_candidates.json
Uma por título (versões iguais/co-op contam uma vez); separa por idioma e por ter stem de voz.
"""
import sys, os, json
from collections import Counter
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from yl import batch, charts, lyrics, twins, align

gold = {os.path.normcase(os.path.abspath(f)) for f in json.load(open(os.path.join(ROOT, 'gold_all.json'), encoding='utf-8-sig'))}
gold_keys = set()
for f in gold:
    try:
        gold_keys.add(twins.key(f))
    except Exception:
        pass
seen, out, C = set(), [], Counter()
for root in sys.argv[1:]:
    for f in batch.find_songs(root):
        try:
            ch = charts.open_chart(f)                      # prefere o original (.bak)
            ev = ch.read_lyrics()[0]
            if len(ev) < 30:
                continue
            words = [w['text'] for w in charts.lyric_events_to_words(ev, ch.tmap)]
            k = twins.key(f)
        except Exception:
            C['erro'] += 1; continue
        if k in seen:
            C['versão repetida'] += 1; continue
        seen.add(k)
        ini = charts.read_ini(f)
        lang = (ini.get('lang') or lyrics.guess_lang([{'words': words}]))[:2]
        st = align.stems(f)
        big = max((os.path.getsize(p) for p in st), default=0)
        has_voc = any(os.path.basename(p).lower().startswith('vocals') and os.path.getsize(p) >= .2 * big for p in st)
        in_gold = os.path.normcase(os.path.abspath(f)) in gold or k in gold_keys
        C[f"{lang} {'stem' if has_voc else 'sem stem'} {'(já no gabarito)' if in_gold else ''}".strip()] += 1
        if not in_gold:
            out.append({'folder': f, 'lang': lang, 'vocal_stem': has_voc, 'words': len(words)})
json.dump(out, open(os.path.join(ROOT, 'reports', 'gold_candidates.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
for k, v in sorted(C.items()):
    print(f'{v:5}  {k}')
print('candidatos novos:', len(out), Counter(o['lang'] for o in out))
