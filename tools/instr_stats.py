"""Estatísticas de voz (detector de instrumental) de cada aligner em músicas instrumentais conhecidas. Só números.

Uso: python tools/instr_stats.py lista.json   (usa a voz já no cache; não separa de novo)
"""
import sys, os, json, glob
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from run import cache_dir
from yl import align, aligners
folders = json.load(open(sys.argv[1], encoding='utf-8-sig'))
for f in folders:
    cd = cache_dir(f)
    wavs = [p for p in glob.glob(os.path.join(cd, 'vocals16k*.wav')) if '_mix' not in os.path.basename(p)]
    if not wavs:
        print(f'{os.path.basename(f)[:30]:30} sem voz no cache'); continue
    row = []
    for a in ('mms', 'w2v-960h', 'alt-dsing'):
        with aligners.using(a):
            align.emission(wavs[0])
            s = align.LAST_STATS
            q = dict(s, vocal_rms_frac=s.get('vocal_rms_frac', 0))
            row.append(f"{a}: cps={q['chars_per_s']:.2f} voiced={q['voiced_win_frac']:.2f} -> "
                       f"{'INSTR' if align.is_instrumental(q) else 'voz'}")
    print(f'{os.path.basename(f)[:30]:30} | ' + ' | '.join(row), flush=True)
