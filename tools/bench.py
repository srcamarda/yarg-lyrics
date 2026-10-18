"""Mede tempo de Demucs e da emissão do alinhador numa pasta (cache temporário). Só tempos."""
import sys, os, time, tempfile, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from yl import align
import torch
folder = sys.argv[1]
print('device', align.DEVICE, torch.__version__)
tmp = tempfile.mkdtemp()
try:
    t = time.time(); wav, how = align.vocals_16k(folder, tmp); t_dem = time.time() - t
    t = time.time(); align._get_model(); t_load = time.time() - t
    t = time.time(); em, ratio, dur = align.emission(wav); t_em = time.time() - t
    print(f'audio {dur:.0f}s | vocals({how}) {t_dem:.1f}s | model load {t_load:.1f}s | emission {t_em:.1f}s | frames {em.shape[0]}')
finally:
    shutil.rmtree(tmp, ignore_errors=True)
