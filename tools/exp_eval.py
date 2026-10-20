"""Avalia variantes de alinhamento no gabarito, a partir dos resultados guardados no cache. Só números.

Variantes: MMS (atual), Whisper, ajuste à grade da música (snap), consenso MMS x Whisper.
Uso: python tools/exp_eval.py <tag> [--json saida.json]
"""
import sys, os, json, difflib, statistics, copy
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from run import cache_dir
from yl import charts, align

n = lambda s: align.norm_word(s, 'pt')
BAD_LINE = 0.5
WHISPER_BIAS = 0.29

# ---------------------------------------------------------------- métricas
def pairs(ref, phrases, min_block=3):
    """[(linha, erro_s)] para palavras casadas com o gabarito (blocos >= 3 palavras, igual ao run.evaluate)."""
    refw = [w for w in ref if n(w['text'])]
    pred, owner = [], []
    for k, p in enumerate(phrases):
        for w in p['words']:
            if n(w['text']):
                pred.append(w); owner.append(k)
    sm = difflib.SequenceMatcher(None, [n(w['text']) for w in refw], [n(w['text']) for w in pred], autojunk=False)
    out = []
    for b in sm.get_matching_blocks():
        if b.size >= min_block:
            out += [(owner[b.b + m], pred[b.b + m]['t'] - refw[b.a + m]['t']) for m in range(b.size)]
    return out

def song_metrics(ref, phrases):
    pr = pairs(ref, phrases)
    if not pr:
        return None
    ab = [abs(e) for _, e in pr]
    lines = {}
    for k, e in pr:
        lines.setdefault(k, []).append(abs(e))
    lerr = {k: statistics.median(v) for k, v in lines.items() if len(v) >= 2}
    return {'errs': ab, 'signed': [e for _, e in pr], 'line_err': lerr}

def summarize(ms):
    ms = [m for m in ms if m]
    ab = sorted(e for m in ms for e in m['errs'])
    le = [e for m in ms for e in m['line_err'].values()]
    per_song_over1 = [sum(e > 1 for e in m['errs']) / len(m['errs']) for m in ms]
    return {'songs': len(ms), 'words': len(ab),
            'median_ms': round(statistics.median(ab) * 1000),
            'within_100': round(sum(e <= .1 for e in ab) / len(ab), 3),
            'within_250': round(sum(e <= .25 for e in ab) / len(ab), 3),
            'over_1s': round(sum(e > 1 for e in ab) / len(ab), 3),
            'bad_lines': round(sum(e > BAD_LINE for e in le) / len(le), 3),
            'bias_ms': round(statistics.median(e for m in ms for e in m['signed']) * 1000),
            'songs_over1_gt10pct': sum(x > .10 for x in per_song_over1)}

# ---------------------------------------------------------------- variantes
def snap(phrases, tmap, div=4, thr=0.06):
    """Puxa o início de cada palavra p/ a subdivisão mais próxima (div=4 -> semicolcheia) se estiver a <= thr s."""
    g = tmap.res / div
    out = copy.deepcopy(phrases)
    for p in out:
        for w in p['words']:
            tk = tmap.s2t(w['t'])
            ts = tmap.t2s(round(tk / g) * g)
            if abs(ts - w['t']) <= thr:
                w['t'] = ts
        # mantém ordem
        for a, b in zip(p['words'], p['words'][1:]):
            if b['t'] < a['t']:
                b['t'] = a['t']
    return out

def shift(phrases, s):
    out = copy.deepcopy(phrases)
    for p in out:
        for w in p['words']:
            w['t'] += s
    return out

def line_start(p):
    return p['words'][0]['t']

def consensus(mms, wh, mode, thr=0.5):
    """Combina por linha (mesmas linhas/palavras nos dois)."""
    if len(mms) != len(wh) or any(len(a['words']) != len(b['words']) for a, b in zip(mms, wh)):
        return None
    out = []
    for a, b in zip(mms, wh):
        d = abs(line_start(a) - line_start(b))
        if mode == 'whisper_if_disagree':          # discordou muito: confia no Whisper (mais robusto a canto)
            out.append(b if d > thr else a)
        elif mode == 'closest_lrc':                # discordou: fica com quem está mais perto do tempo do LRCLIB
            lrc = a.get('lrc_t')
            if d > thr and lrc is not None:
                out.append(b if abs(line_start(b) - lrc) < abs(line_start(a) - lrc) else a)
            else:
                out.append(a)
        elif mode == 'closest_lrc_keep_mms_words':  # idem, mas usa só o início da linha do Whisper e o ritmo do MMS
            lrc = a.get('lrc_t')
            if d > thr and lrc is not None and abs(line_start(b) - lrc) < abs(line_start(a) - lrc):
                s = line_start(b) - line_start(a)
                c = copy.deepcopy(a)
                for w in c['words']:
                    w['t'] += s
                    if w.get('end') is not None:
                        w['end'] += s
                out.append(c)
            else:
                out.append(a)
        elif mode == 'shift_mms_to_whisper':       # discordou: desloca a linha do MMS p/ começar onde o Whisper diz
            if d > thr:
                s = line_start(b) - line_start(a)
                c = copy.deepcopy(a)
                for w in c['words']:
                    w['t'] += s
                    if w.get('end') is not None:
                        w['end'] += s
                out.append(c)
            else:
                out.append(a)
        elif mode == 'avg_words':                  # concordaram (< thr): média palavra a palavra; senão MMS
            if d <= thr:
                c = copy.deepcopy(a)
                for wa, wb in zip(c['words'], b['words']):
                    if abs(wa['t'] - wb['t']) < 0.25:
                        wa['t'] = (wa['t'] + wb['t']) / 2
                out.append(c)
            else:
                out.append(a)
    return out

def disagreement_flags(mms, wh, thr):
    if len(mms) != len(wh):
        return None
    return [abs(line_start(a) - line_start(b)) > thr for a, b in zip(mms, wh)]

# ---------------------------------------------------------------- main
if __name__ == '__main__':
    tag = sys.argv[1]
    folders = json.load(open(os.path.join(ROOT, 'gold_all.json'), encoding='utf-8-sig'))
    V = {}
    flagstats = {}
    def add(name, ref, ph):
        V.setdefault(name, []).append(song_metrics(ref, ph) if ph else None)
    for f in folders:
        cd = cache_dir(f)
        pm, pw = os.path.join(cd, f'aligned_eval_{tag}.json'), os.path.join(cd, f'aligned_whisper_{tag}.json')
        if tag == 'legacy':
            pm = os.path.join(cd, 'aligned.json')
        if not os.path.exists(pm):
            continue
        ch = charts.open_chart(f)
        ref = charts.lyric_events_to_words(ch.read_lyrics()[0], ch.tmap)
        mms = json.load(open(pm, encoding='utf-8'))
        mms = mms['phrases'] if isinstance(mms, dict) else mms
        add('MMS (atual)', ref, mms)
        add('MMS + atraso fixo 20ms', ref, shift(mms, 0.02))
        add('MMS + 20ms + grade 1/8 ±60ms', ref, snap(shift(mms, 0.02), ch.tmap, 2, 0.06))
        for div, thr in ((4, 0.04), (4, 0.06), (4, 0.08), (8, 0.04), (2, 0.06)):
            add(f'MMS + grade 1/{div*4} ±{int(thr*1000)}ms', ref, snap(mms, ch.tmap, div, thr))
        if os.path.exists(pw):
            wh = json.load(open(pw, encoding='utf-8'))['phrases']
            add('Whisper', ref, wh)
            add('Whisper + grade 1/16 ±60ms', ref, snap(wh, ch.tmap, 4, 0.06))
            for mode in ('whisper_if_disagree', 'closest_lrc', 'shift_mms_to_whisper', 'avg_words'):
                add(f'Consenso: {mode}', ref, consensus(mms, wh, mode))
            wh2 = shift(wh, WHISPER_BIAS)              # Whisper adianta ~0,29 s de forma sistemática
            add('Whisper + atraso 290ms', ref, wh2)
            add('Consenso: closest_lrc (Wh+290ms)', ref, consensus(mms, wh2, 'closest_lrc'))
            for thr in (0.3, 0.5, 1.0):
                add(f'Consenso: lrc, só início Wh ±{thr}s', ref, consensus(mms, wh2, 'closest_lrc_keep_mms_words', thr))
            add('Consenso lrc 0.5 + 20ms + grade 1/8', ref,
                snap(shift(consensus(mms, wh2, 'closest_lrc_keep_mms_words', 0.5), 0.02), ch.tmap, 2, 0.06))
            # discordância como sinal de linha suspeita x flags atuais
            sm = song_metrics(ref, mms)
            if sm:
                for thr in (0.3, 0.5, 1.0):
                    fl = disagreement_flags(mms, wh, thr)
                    if fl is None:
                        continue
                    for k, e in sm['line_err'].items():
                        s = flagstats.setdefault(thr, {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0, 'f2_tp': 0, 'f2_fp': 0, 'f2_fn': 0,
                                                       'or_tp': 0, 'or_fp': 0, 'or_fn': 0})
                        bad, flg, f2 = e > BAD_LINE, fl[k], mms[k].get('flag') == 2
                        s['tp' if bad and flg else 'fp' if flg else 'fn' if bad else 'tn'] += 1
                        if f2 or bad:
                            s['f2_tp' if (bad and f2) else 'f2_fp' if f2 else 'f2_fn'] += 1
                        if (f2 or flg) or bad:
                            s['or_tp' if (bad and (f2 or flg)) else 'or_fp' if (f2 or flg) else 'or_fn'] += 1
    res = {k: summarize(v) for k, v in V.items() if any(v)}
    hdr = f"{'variante':38} {'músicas':>7} {'palavras':>8} {'med':>5} {'≤100':>5} {'≤250':>5} {'>1s':>5} {'lin.ruins':>9} {'viés':>5} {'mús>10%':>7}"
    print(hdr)
    for k, r in res.items():
        print(f"{k:38} {r['songs']:7} {r['words']:8} {r['median_ms']:5} {r['within_100']:5.3f} {r['within_250']:5.3f} "
              f"{r['over_1s']:5.3f} {r['bad_lines']:9.3f} {r['bias_ms']:5} {r['songs_over1_gt10pct']:7}")
    pr = lambda tp, fp, fn: (tp / max(1, tp + fp), tp / max(1, tp + fn))
    for thr, s in sorted(flagstats.items()):
        p, r = pr(s['tp'], s['fp'], s['fn'])
        p2, r2 = pr(s['f2_tp'], s['f2_fp'], s['f2_fn'])
        po, ro = pr(s['or_tp'], s['or_fp'], s['or_fn'])
        print(f"suspeita por discordância >{thr}s: precisão {p:.2f} cobertura {r:.2f} | flag 2 atual: {p2:.2f}/{r2:.2f} | "
              f"flag 2 OU discordância: {po:.2f}/{ro:.2f}")
    if '--json' in sys.argv:
        json.dump({'variants': res, 'flags': flagstats}, open(sys.argv[sys.argv.index('--json') + 1], 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
