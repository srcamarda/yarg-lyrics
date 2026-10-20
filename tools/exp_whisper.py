"""Experimento 2: alinhar a MESMA letra com Whisper (stable-ts align) sobre o MESMO arquivo de voz usado pelo MMS.

Lê cache/<música>/aligned_eval_<tag>.json (gerado por run.py --eval) e grava aligned_whisper_<tag>.json
no mesmo formato (frases -> palavras com t/end em tempo de chart). Só imprime números.

Uso: python tools/exp_whisper.py <tag> [modelo=large-v3] [lista=gold_all.json]
"""
import sys, os, json, time, difflib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from run import cache_dir
from yl import align
import torch
import stable_whisper

tag = sys.argv[1]
model_name = sys.argv[2] if len(sys.argv) > 2 else 'large-v3'
folders = json.load(open(sys.argv[3] if len(sys.argv) > 3 else os.path.join(ROOT, 'gold_all.json'), encoding='utf-8-sig'))
n = lambda s: align.norm_word(s, 'pt')
model = stable_whisper.load_model(model_name, device=align.DEVICE,
                                  download_root=os.path.join(ROOT, 'cache', 'models', 'whisper'))

def transfer(phrases, wwords, delay):
    """Copia os tempos das palavras do Whisper para as nossas palavras (casamento por sequência normalizada)."""
    ours = [(i, j, n(w['text'])) for i, p in enumerate(phrases) for j, w in enumerate(p['words'])]
    theirs = [(n(w.word), w.start - delay, w.end - delay, w.probability) for w in wwords]
    sm = difflib.SequenceMatcher(None, [o[2] for o in ours], [t[0] for t in theirs], autojunk=False)
    got = {}
    for b in sm.get_matching_blocks():
        for k in range(b.size):
            got[b.a + k] = theirs[b.b + k]
    # palavras sem par: interpola entre vizinhos com par
    idx = sorted(got)
    times = []
    for k in range(len(ours)):
        if k in got:
            times.append(got[k][1:]); continue
        prev = max((x for x in idx if x < k), default=None)
        nxt = min((x for x in idx if x > k), default=None)
        if prev is None and nxt is None:
            times.append((None, None, 0.0)); continue
        if prev is None:
            t = got[nxt][1]
        elif nxt is None:
            t = got[prev][2]
        else:
            t = got[prev][2] + (got[nxt][1] - got[prev][2]) * (k - prev) / (nxt - prev)
        times.append((t, t + 0.05, 0.0))
    out, k = [], 0
    for p in phrases:
        ws = []
        for w in p['words']:
            t, e, pr = times[k]; k += 1
            ws.append({'t': t, 'end': e, 'text': w['text'], 'prob': pr, 'matched': (k - 1) in got})
        if all(w['t'] is not None for w in ws):
            out.append({'start': ws[0]['t'], 'end': max(w['end'] for w in ws), 'words': ws, 'lrc_t': p.get('lrc_t')})
    return out, len(got) / max(1, len(ours))

t_all = time.time()
for i, f in enumerate(folders, 1):
    cd = cache_dir(f)
    src = os.path.join(cd, f'aligned_eval_{tag}.json')
    dst = os.path.join(cd, f'aligned_whisper_{tag}.json')
    name = os.path.basename(f)[:36]
    if not os.path.exists(src):
        print(f'[{i}/{len(folders)}] sem {os.path.basename(src)}  {name}', flush=True); continue
    if os.path.exists(dst):
        print(f'[{i}/{len(folders)}] cache  {name}', flush=True); continue
    d = json.load(open(src, encoding='utf-8'))
    text = '\n'.join(' '.join(w['text'] for w in p['words']) for p in d['phrases'])
    t = time.time()
    try:
        res = model.align(d['vocals_wav'], text, language=d['lang'], original_split=True, verbose=None)
        phrases, frac = transfer(d['phrases'], res.all_words(), d['delay'])
        json.dump({'phrases': phrases, 'matched_frac': frac, 'model': model_name},
                  open(dst, 'w', encoding='utf-8'), ensure_ascii=False)
        print(f'[{i}/{len(folders)}] ok {time.time() - t:5.1f}s casadas={frac:.2f}  {name}', flush=True)
    except Exception as e:
        print(f'[{i}/{len(folders)}] ERRO {type(e).__name__}: {str(e)[:120]}  {name}', flush=True)
    torch.cuda.empty_cache()
print(f'total {(time.time() - t_all) / 60:.1f} min')
