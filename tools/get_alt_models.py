"""Baixa os checkpoints do ALT (Ou/Gu et al., ISMIR 2022) do Google Drive dos autores. Só o necessário p/ inferência CTC.

Uso: python tools/get_alt_models.py [--meta]   (--meta: só os .yaml)
"""
import os, sys, re
import gdown
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDERS = {'dsing': 'https://drive.google.com/drive/folders/1wcvkkZop16ytTuu6JDahUpZ6nsDbD1jN',
           'dali': 'https://drive.google.com/drive/folders/15e0IBLJHtTBpKfI0ju4EFR0dxLM63LW-'}
WANT = ('hyperparams.yaml', 'CKPT.yaml', 'model.ckpt', 'wav2vec2.ckpt')
meta_only = '--meta' in sys.argv
for name, url in FOLDERS.items():
    out = os.path.join(ROOT, 'cache', 'models', 'alt', name)
    fs = gdown.download_folder(url=url, skip_download=True, quiet=True)
    for f in fs:
        base = os.path.basename(f.path.replace('\\', '/'))
        if base not in WANT or (meta_only and not base.endswith('.yaml')):
            continue
        if base != 'hyperparams.yaml' and 'CKPT+' not in f.path:
            continue
        m = re.search(r'(CKPT\+[^\\/]+)', f.path)
        dst = os.path.join(out, m.group(1) if m else '', base)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            print('já existe', name, os.path.relpath(dst, out)); continue
        gdown.download(id=f.id, output=dst, quiet=True)
        print('baixado', name, os.path.relpath(dst, out), f'{os.path.getsize(dst) / 2**20:.1f} MB', flush=True)
