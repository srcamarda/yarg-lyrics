"""Atividade vocal por música (sem letra envolvida): speech_win_frac (CTC) e vocal_rms_frac (energia do stem)."""
import sys, os, glob
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from yl import align
from run import cache_dir
for pat in sys.argv[1:]:
    for f in sorted(glob.glob(pat)):
        if not os.path.isdir(f):
            continue
        try:
            wav, how = align.vocals_16k(f, cache_dir(f))
            align.emission(wav)
            s = align.LAST_STATS
            print(f"cps={s['chars_per_s']:5.2f} vwin={s['voiced_win_frac']:.3f} rms={s['vocal_rms_frac']:.3f} {how:6} {os.path.basename(f)[:60]}", flush=True)
        except Exception as e:
            print(f"erro {type(e).__name__}: {e} | {os.path.basename(f)}", flush=True)
