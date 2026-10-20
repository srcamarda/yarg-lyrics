"""Pré-separa a voz (só o separador, sem carregar o alinhador) para uma lista de pastas. Só tempos.

Uso: python tools/presep.py lista.json   (respeita YL_SEPARATOR e YL_IGNORE_VOCAL_STEM)
"""
import sys, os, json, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from run import cache_dir
from yl import align
folders = json.load(open(sys.argv[1], encoding='utf-8-sig'))
t0 = time.time()
for i, f in enumerate(folders, 1):
    t = time.time()
    try:
        _, how = align.vocals_16k(f, cache_dir(f))
    except Exception as e:
        how = f'ERRO {type(e).__name__}'
    print(f'[{i}/{len(folders)}] {how:8} {time.time() - t:6.1f}s  {os.path.basename(f)[:40]}', flush=True)
print(f'total {(time.time() - t0) / 60:.1f} min')
