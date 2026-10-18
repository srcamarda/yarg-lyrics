"""yarg-lyrics: busca letra no LRCLIB, alinha com a voz e grava num chart novo.

Uso:
  python run.py "<pasta da música>" [...]        -> grava notes.autolyrics.(chart|mid) na pasta
  python run.py --eval "<pasta com letra>" [...]  -> compara com a letra existente (grava só no cache)
  python run.py --list arquivo.json [--eval]      -> lista de pastas em JSON
Saída no console: só métricas (nunca o texto da letra).
"""
import sys, os, re, json, time, difflib, statistics, hashlib
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from yl import charts, lyrics, align

def cache_dir(folder):
    h = hashlib.md5(os.path.abspath(folder).encode('utf-8')).hexdigest()[:8]
    d = os.path.join(ROOT, 'cache', re.sub(r'[^\w\- ]', '_', os.path.basename(folder))[:60] + '_' + h)
    os.makedirs(d, exist_ok=True)
    return d

def song_len_s(ini):
    try:
        return float(ini.get('song_length')) / 1000.0
    except (TypeError, ValueError):
        return 0.0

def evaluate(ref_words, pred_phrases, min_block=3):
    n = lambda s: align.norm_word(s, 'pt')
    ref = [w for w in ref_words if n(w['text'])]
    pred = [w for p in pred_phrases for w in p['words'] if n(w['text'])]
    sm = difflib.SequenceMatcher(None, [n(w['text']) for w in ref], [n(w['text']) for w in pred], autojunk=False)
    errs = []
    for b in sm.get_matching_blocks():
        if b.size >= min_block:
            errs += [pred[b.b + k]['t'] - ref[b.a + k]['t'] for k in range(b.size)]
    if not errs:
        return {'ref_words': len(ref), 'matched': 0}
    ab = sorted(abs(e) for e in errs)
    return {'ref_words': len(ref), 'pred_words': len(pred), 'matched': len(ab),
            'coverage': round(len(ab) / len(ref), 3),
            'median_ms': round(statistics.median(ab) * 1000),
            'p90_ms': round(ab[int(0.9 * (len(ab) - 1))] * 1000),
            'bias_ms': round(statistics.median(errs) * 1000),
            'within_100ms': round(sum(a <= .1 for a in ab) / len(ab), 3),
            'within_250ms': round(sum(a <= .25 for a in ab) / len(ab), 3),
            'over_1s': round(sum(a > 1 for a in ab) / len(ab), 3)}

def process(folder, do_eval=False, force=False):
    t0 = time.time()
    folder = os.path.abspath(folder)
    cd = cache_dir(folder)
    ini = charts.read_ini(folder)
    ch = charts.open_chart(folder)
    artist, title = ini.get('artist', ''), ini.get('name', '')
    rep = {'folder': folder, 'artist': artist, 'title': title, 'format': ch.kind}
    if ch.has_lyrics() and not do_eval and not force:
        rep['status'] = 'skip: já tem letra'
        return rep
    rec = lyrics.fetch(artist, title, song_len_s(ini), os.path.join(cd, 'lrclib.json'))
    lines, src = lyrics.from_record(rec)
    if not lines:
        local = os.path.join(folder, 'lyrics.txt')
        if os.path.exists(local):
            lines, src = lyrics.parse_lrc(open(local, encoding='utf-8').read()), 'local'
    if not lines:
        rep['status'] = 'sem letra (LRCLIB vazio e sem lyrics.txt)'
        return rep
    rep['lyrics_source'] = src
    if rec:
        rep['lrclib'] = {'id': rec['id'], 'duration_delta_s': rec['duration_delta']}
    lang = (ini.get('lang') or lyrics.guess_lang(lines))[:2]
    rep['lang'] = lang
    wav, how = align.vocals_16k(folder, cd)
    rep['vocals'] = how
    if src in ('synced', 'local') and all(l['t'] is not None for l in lines):
        raw, dur, off, nfix = align.align_hybrid(lines, wav, lang)
        rep['mode'] = 'hybrid'; rep['lrc_offset_s'] = round(off, 2); rep['lines_realigned'] = nfix
    else:
        raw, dur = align.align(lines, wav, lang)
        rep['mode'] = 'global'
    delay = charts.audio_delay(folder, ch)
    phrases = align.finalize(raw, delay)
    rep['quality'] = align.quality(phrases, delay)
    rep['phrases'] = len(phrases)
    rep['words'] = sum(len(p['words']) for p in phrases)
    json.dump(phrases, open(os.path.join(cd, 'aligned.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    ext = '.chart' if ch.kind == 'chart' else '.mid'
    if do_eval:
        ref = charts.lyric_events_to_words(ch.read_lyrics()[0], ch.tmap)
        rep['eval'] = evaluate(ref, phrases)
        out = os.path.join(cd, 'notes.autolyrics' + ext)
    else:
        out = os.path.join(folder, 'notes.autolyrics' + ext)
    ch.write_lyrics(phrases, out)
    rep['output'] = out
    rep['status'] = align.verdict(rep)
    rep['seconds'] = round(time.time() - t0, 1)
    return rep

if __name__ == '__main__':
    args = sys.argv[1:]
    do_eval, force = '--eval' in args, '--force' in args
    folders = []
    if '--list' in args:
        folders += json.load(open(args[args.index('--list') + 1], encoding='utf-8-sig'))
    folders += [a for i, a in enumerate(args) if not a.startswith('--') and (i == 0 or args[i - 1] != '--list')]
    os.makedirs(os.path.join(ROOT, 'reports'), exist_ok=True)
    rpath = os.path.join(ROOT, 'reports', time.strftime('%Y%m%d-%H%M%S') + ('-eval' if do_eval else '') + '.jsonl')
    for f in folders:
        try:
            r = process(f, do_eval, force)
        except Exception as e:
            import traceback; traceback.print_exc()
            r = {'folder': f, 'status': f'erro: {type(e).__name__}: {e}'}
        with open(rpath, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')
        print(json.dumps({k: v for k, v in r.items() if k not in ('folder', 'output')}, ensure_ascii=False), flush=True)
    print('report:', rpath)
