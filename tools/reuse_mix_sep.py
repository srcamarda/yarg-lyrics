"""Músicas SEM stem de voz: a voz separada 'do mix' e a 'normal' são o mesmo arquivo. Copia a do mix p/ o nome normal
(se faltar), p/ não separar de novo. Uso: python tools/reuse_mix_sep.py lista.json"""
import sys, os, json, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from run import cache_dir
from yl import align
n = 0
for f in json.load(open(sys.argv[1], encoding='utf-8-sig')):
    st = align.stems(f)
    big = max((os.path.getsize(p) for p in st), default=0)
    if any(os.path.basename(p).lower().startswith('vocals') and os.path.getsize(p) >= .2 * big for p in st):
        continue                                             # tem stem de voz: a versão normal usa o stem
    cd = cache_dir(f)
    if os.path.exists(os.path.join(cd, 'mix.wav')):
        continue                                             # separação em andamento nesta pasta
    for src in os.listdir(cd):
        if src.startswith('vocals16k_mix') and src.endswith('.wav'):
            dst = os.path.join(cd, src.replace('vocals16k_mix', 'vocals16k', 1))
            if not os.path.exists(dst):
                shutil.copy2(os.path.join(cd, src), dst); n += 1
print('copiados', n)
