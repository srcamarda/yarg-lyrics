"""Gera letra, pasta por pasta e em ordem, para as músicas SEM letra (nem oficial, nem gerada), pela fila da interface.

Pula: .nolyrics, letra oficial, letra já gerada (notes.autolyrics.*). Espera cada pasta terminar antes da próxima.
Uso: python tools/batch_folders.py <raiz> [--contar] [--pular "Nome da pasta" ...]
Log: logs/batch_folders.log (só nomes, contagens e status)
"""
import sys, os, json, time, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from yl import batch, charts
API = 'http://127.0.0.1:8765'
LOG = os.path.join(ROOT, 'logs', 'batch_folders.log')

def log(msg):
    line = time.strftime('%H:%M ') + msg
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as fh:
        fh.write(line + '\n')

def call(path, body=None):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def restart_server():
    """Servidor novo antes de cada pasta: depois de alinhar, o processo da interface segura ~2,4 GB de VRAM e o
    separador (pico ~8 GB) passava p/ a memória compartilhada (~4 min/música em vez de ~1). Novo = 0 GB até alinhar."""
    import subprocess
    out = subprocess.run(['powershell', '-NoProfile', '-Command',
                          '(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue).OwningProcess'],
                         capture_output=True, text=True).stdout.split()
    for pid in set(out):
        subprocess.run(['powershell', '-NoProfile', '-Command',
                        f'$p=(Get-CimInstance Win32_Process -Filter "ProcessId={pid}").ParentProcessId; '
                        f'Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue; '
                        f'if ($p) {{ Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }}'], capture_output=True)
    time.sleep(3)
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    for k in ('YL_ALIGNER', 'YL_SEPARATOR', 'YL_IGNORE_VOCAL_STEM', 'YL_SECOND', 'YL_ALT_CKPT'):
        env.pop(k, None)                               # o servidor sempre no padrão
    py = os.path.join(ROOT, '.venv-rocm', 'Scripts', 'python.exe')
    subprocess.Popen([py, os.path.join(ROOT, 'ui', 'server.py')], cwd=ROOT, env=env,
                     stdout=open(os.path.join(ROOT, 'logs', 'ui.log'), 'a', encoding='utf-8'),
                     stderr=open(os.path.join(ROOT, 'logs', 'ui.err'), 'a', encoding='utf-8'),
                     creationflags=0x08000000)         # CREATE_NO_WINDOW
    for _ in range(60):
        time.sleep(2)
        try:
            call('/api/job'); return
        except Exception:
            pass
    raise RuntimeError('servidor não subiu')

def todo(folder):
    out = []
    for f in batch.find_songs(folder):
        if os.path.exists(os.path.join(f, '.nolyrics')) or batch.generated(f):
            continue
        if any(x.lower().startswith('notes.') and x.lower().endswith('.bak') for x in os.listdir(f)):
            continue                                   # já aplicada: a letra está no chart (o .bak é o original)
        try:
            if charts.open_chart(f).has_lyrics():
                continue
        except Exception:
            continue
        out.append(f)
    return out

root = sys.argv[1]
skip = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == '--pular' and i + 1 < len(sys.argv)]
folders = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)) and d not in skip)
plan = [(d, todo(os.path.join(root, d))) for d in folders]
for d, l in plan:
    print(f'{len(l):4}  {d}')
print(f'{sum(len(l) for _, l in plan):4}  total')
if '--contar' in sys.argv:
    sys.exit(0)
for d, l in plan:
    if not l:
        continue
    while call('/api/job')['running']:
        time.sleep(30)
    restart_server()
    log(f'== {d}: {len(l)} músicas')
    call('/api/run', {'folders': l, 'force': False})
    time.sleep(10)
    while True:
        j = call('/api/job')
        if not j['running']:
            break
        time.sleep(60)
    from collections import Counter
    c = Counter(str(x.get('status')).split(' (')[0].split(':')[0] for x in j.get('log', []))
    log(f'   {d}: {dict(c)}')
log('== fim')
