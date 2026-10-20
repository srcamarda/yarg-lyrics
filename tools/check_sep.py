"""Confere as vozes separadas no cache: duração e energia, por separador. Só números."""
import sys, os, json, glob
import numpy as np, soundfile as sf
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from run import cache_dir
folders = json.load(open(sys.argv[1], encoding='utf-8-sig'))
for f in folders:
    cd = cache_dir(f)
    row = []
    for p in sorted(glob.glob(os.path.join(cd, 'vocals16k*.wav'))):
        x, sr = sf.read(p, dtype='float32')
        rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0
        row.append(f"{os.path.basename(p)[9:-4] or '(stem)':22} {len(x)/sr:6.1f}s rms={rms:.3f}")
    print(f"{os.path.basename(f)[:28]:28} | " + ' | '.join(row))
