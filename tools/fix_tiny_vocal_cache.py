"""Apaga o vocals16k.wav do cache de músicas cujo 'stem de voz' era um arquivo minúsculo (bug corrigido)."""
import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from yl import batch, align
from run import cache_dir
for root in sys.argv[1:]:
    for f in batch.find_songs(root):
        st = align.stems(f)
        voc = [p for p in st if os.path.basename(p).lower().startswith('vocals')]
        if not voc:
            continue
        big = max(os.path.getsize(p) for p in st)
        if all(os.path.getsize(p) < 0.2 * big for p in voc):
            w = os.path.join(cache_dir(f), 'vocals16k.wav')
            if os.path.exists(w):
                os.remove(w)
            print(f)
