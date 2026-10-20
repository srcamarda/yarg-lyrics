"""Lista músicas com letra GERADA e NÃO aplicada numa pasta, p/ regenerar. Só contagens e nomes.

Pula: aplicadas (.bak), com ajustes manuais (edited), copiadas de outra versão (cópia), .nolyrics.
Uso: python tools/regen_list.py <pasta> <saida.json>
"""
import sys, os, json, shutil
from collections import Counter
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from yl import batch
from run import cache_dir

state = json.load(open(os.path.join(ROOT, 'ui_state.json'), encoding='utf-8'))
key = lambda f: os.path.normcase(os.path.abspath(f))
C, out, skipped = Counter(), [], []
for f in batch.find_songs(sys.argv[1]):
    files = {x.lower() for x in os.listdir(f)}
    s = state.get(key(f), {})
    rep = s.get('report') or {}
    gen = batch.generated(f)
    applied = any(x.startswith('notes.') and x.endswith('.bak') for x in files)
    if os.path.exists(os.path.join(f, '.nolyrics')):
        C['.nolyrics'] += 1; continue
    if applied:
        C['já aplicada'] += 1; continue
    if not gen:
        C['sem letra gerada'] += 1; continue
    if s.get('edited'):
        C['gerada, com ajustes manuais (pula)'] += 1; skipped.append(os.path.basename(f)); continue
    if rep.get('lyrics_source') == 'cópia':
        C['gerada por cópia da versão oficial (pula)'] += 1; skipped.append(os.path.basename(f)); continue
    C['gerada, não aplicada -> regenerar' + (' (estava aprovada)' if s.get('approved') or rep.get('approved') else '')] += 1
    # guarda a versão anterior no cache, caso precise voltar
    bk = os.path.join(cache_dir(f), 'antes_regen')
    os.makedirs(bk, exist_ok=True)
    shutil.copy2(gen, os.path.join(bk, os.path.basename(gen)))
    out.append(f)
json.dump(out, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
for k, v in sorted(C.items()):
    print(f'{v:4}  {k}')
print('pulados:', skipped)
