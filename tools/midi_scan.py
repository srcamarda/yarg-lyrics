"""Procura .mid cuja contagem de trilhas no cabeçalho não bate com as trilhas válidas, ou com lixo entre trilhas.
Com --consertar, regrava só as trilhas válidas (cópia do arquivo anterior vai p/ cache/midi_reparo/). Só nomes e números.

Uso: python tools/midi_scan.py <raiz> [--consertar] [--so-aplicadas]
"""
import sys, os, struct, shutil, hashlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from yl import batch, midifix

def raw_scan(b):
    hl = struct.unpack('>I', b[4:8])[0]
    ntr = struct.unpack('>H', b[10:12])[0]
    i, valid, junk = 8 + hl, 0, 0
    while i + 8 <= len(b):
        if b[i:i + 4] != b'MTrk':
            j = b.find(b'MTrk', i + 1)
            junk += (j if j >= 0 else len(b)) - i
            if j < 0:
                break
            i = j; continue
        ln = struct.unpack('>I', b[i + 4:i + 8])[0]
        if i + 8 + ln > len(b):
            junk += len(b) - i; break
        valid += 1; i += 8 + ln
    return ntr, valid, junk

fix, only_applied = '--consertar' in sys.argv, '--so-aplicadas' in sys.argv
n = bad = fixed = 0
for f in batch.find_songs(sys.argv[1]):
    files = {x.lower(): x for x in os.listdir(f)}
    if 'notes.mid' not in files or (only_applied and 'notes.mid.bak' not in files):
        continue
    p = os.path.join(f, files['notes.mid'])
    b = open(p, 'rb').read()
    if b[:4] != b'MThd':
        continue
    n += 1
    ntr, valid, junk = raw_scan(b)
    if ntr == valid and not junk:
        continue
    bad += 1
    applied = 'notes.mid.bak' in files
    print(f'{os.path.basename(os.path.dirname(f))[:22]:22} | {os.path.basename(f)[:40]:40} | cabeçalho {ntr} trilhas, '
          f'válidas {valid}, lixo {junk} bytes{" | letra aplicada" if applied else ""}')
    if fix and ntr != valid:                      # só os que o YARG recusa (contagem errada)
        bk = os.path.join(ROOT, 'cache', 'midi_reparo', hashlib.md5(f.encode()).hexdigest()[:8] + '_' + os.path.basename(f)[:40])
        os.makedirs(bk, exist_ok=True)
        shutil.copy2(p, os.path.join(bk, 'notes.mid'))
        hdr, chunks = midifix.split(b)
        fmt, _, div = struct.unpack('>HHH', hdr[:6])
        open(p, 'wb').write(b'MThd' + struct.pack('>IHHH', 6, 1, len(chunks), div) + b''.join(chunks))
        ntr2, valid2, junk2 = raw_scan(open(p, 'rb').read())
        print(f'   consertado: cabeçalho {ntr2}, válidas {valid2}, lixo {junk2}')
        fixed += 1
print(f'{n} arquivos .mid verificados; {bad} com problema; {fixed} consertados')
