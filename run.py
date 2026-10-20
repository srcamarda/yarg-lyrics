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
    if os.path.exists(os.path.join(folder, '.nolyrics')):          # marcado à mão: não pôr letra
        rep['status'] = 'ignorado (.nolyrics)'
        return rep
    if ch.has_lyrics() and not do_eval:
        rep['status'] = 'skip: já tem letra'
        return rep
    local = os.path.join(folder, 'lyrics.txt')                 # letra manual tem prioridade
    rec = None
    if os.path.exists(local):
        lines, src = lyrics.parse_lrc(lyrics.read_text(local)), 'local'
    else:
        rec = lyrics.fetch(artist, title, song_len_s(ini), os.path.join(cd, 'lrclib.json'))
        lines, src = lyrics.from_record(rec)
    if not lines:
        rep['status'] = 'instrumental (LRCLIB)' if rec and rec.get('instrumental') else 'sem letra (LRCLIB vazio e sem lyrics.txt)'
        return rep
    rep['lyrics_source'] = src
    if rec and not rec.get('instrumental'):
        rep['lrclib'] = {'id': rec['id'], 'duration_delta_s': rec['duration_delta']}
    lang = (ini.get('lang') or lyrics.guess_lang(lines))[:2]
    rep['lang'] = lang
    wav, how = align.vocals_16k(folder, cd)
    rep['vocals'] = how
    from yl import aligners
    rep['aligner'] = aligners.name()
    if src in ('synced', 'local') and all(l['t'] is not None for l in lines):
        raw, dur, off, nfix = align.align_hybrid(lines, wav, lang)
        rep['mode'] = 'hybrid'; rep['lrc_offset_s'] = round(off, 2); rep['lines_realigned'] = nfix
        rep['lines_repaired'] = align.LAST_STATS_EXTRA.get('lines_repaired', 0)
        raw = align.debias(raw)
        second = aligners.second_for(lang)
        if second:                                   # 2ª opinião: consenso por linha, desempate pelo LRCLIB
            stats = dict(align.LAST_STATS)           # estatísticas de voz ficam as do modelo principal
            with aligners.using(second):
                raw2 = align.debias(align.align_hybrid(lines, wav, lang)[0])
            raw, n2 = align.consensus_lrc(raw, raw2)
            align.LAST_STATS.clear(); align.LAST_STATS.update(stats)
            rep['second_opinion'] = second; rep['lines_from_second'] = n2
    else:
        raw, dur = align.align(lines, wav, lang)
        raw = align.debias(raw)
        rep['mode'] = 'global'
    delay = charts.audio_delay(folder, ch)
    phrases = align.finalize(raw, delay)
    rep['quality'] = align.quality(phrases, delay)
    rep['quality'].update(align.LAST_STATS)
    if not do_eval and align.is_instrumental(rep['quality']):
        from yl import batch
        stale = batch.generated(folder)
        if stale:
            os.remove(stale)
        rep['status'] = 'instrumental (sem voz no áudio)'
        rep['seconds'] = round(time.time() - t0, 1)
        return rep
    rep['phrases'] = len(phrases)
    rep['words'] = sum(len(p['words']) for p in phrases)
    json.dump(phrases, open(os.path.join(cd, 'aligned.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    ext = '.chart' if ch.kind == 'chart' else '.mid'
    if do_eval:
        # guarda o resultado por configuração (voz de stem/mix + separador) p/ experimentos offline (tools/exp_*.py)
        tag = ('mix_' if os.environ.get('YL_IGNORE_VOCAL_STEM') == '1' else 'stem_') + \
              re.sub(r'\W+', '', os.path.splitext(align.separator())[0])[:24]
        from yl import aligners
        if aligners.name() != 'mms':
            tag += '_' + re.sub(r'\W+', '', aligners.name())
        if os.environ.get('YL_ALT_CKPT') == 'mid':
            tag += '_mid'
        if rep.get('second_opinion'):
            tag += '_2' + re.sub(r'\W+', '', rep['second_opinion'])
        elif not os.environ.get('YL_ALIGNER'):
            tag += '_padrao'
        json.dump({'vocals_wav': wav, 'delay': delay, 'lang': lang, 'phrases': phrases},
                  open(os.path.join(cd, f'aligned_eval_{tag}.json'), 'w', encoding='utf-8'), ensure_ascii=False)
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
    from yl import batch
    args = sys.argv[1:]
    flag = lambda f: f in args
    def opt(name):
        return [args[i + 1] for i, a in enumerate(args) if a == name and i + 1 < len(args)]
    do_eval, force, do_apply = flag('--eval'), flag('--force'), flag('--apply')
    if flag('--restore'):
        for root in opt('--scan') + [a for a in args if not a.startswith('--') and a not in opt('--scan')]:
            n = sum(batch.restore(f) for f in batch.find_songs(root))
            print(f'restaurados: {n}')
        sys.exit(0)
    folders = []
    for l in opt('--list'):
        folders += json.load(open(l, encoding='utf-8-sig'))
    for root in opt('--scan'):
        folders += list(batch.find_songs(root))
    skip_vals = set(opt('--list')) | set(opt('--scan'))
    folders += [a for a in args if not a.startswith('--') and a not in skip_vals]
    os.makedirs(os.path.join(ROOT, 'reports'), exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S') + ('-eval' if do_eval else '')
    rpath = os.path.join(ROOT, 'reports', stamp + '.jsonl')
    reports, n = [], len(folders)
    print(f'{n} pastas', flush=True)
    for i, f in enumerate(folders, 1):
        if not do_eval and not force and batch.generated(f):
            r = {'folder': f, 'status': 'skip: já gerado (use --force)'}
        else:
            try:
                r = process(f, do_eval, force)
            except Exception as e:
                import traceback; traceback.print_exc()
                r = {'folder': f, 'status': f'erro: {type(e).__name__}: {e}'}
        if do_apply and r.get('status') == 'ok' and not do_eval:
            r['applied'] = batch.apply(f)
        reports.append(r)
        with open(rpath, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')
        print(f"[{i}/{n}] {r.get('status')} | {r.get('artist', '')} - {r.get('title', os.path.basename(f))}", flush=True)
    batch.write_csv(reports, os.path.join(ROOT, 'reports', stamp + '.csv'))
    from collections import Counter
    print(dict(Counter(str(r.get('status')).split(':')[0] for r in reports)))
    print('report:', rpath.replace('.jsonl', '.csv'))
