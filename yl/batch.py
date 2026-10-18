"""Modo lote: varredura de setlists, aplicação com backup e relatório CSV (sem texto de letra)."""
import os, csv, shutil

def find_songs(root):
    for dp, dn, fn in os.walk(root):
        low = {f.lower() for f in fn}
        if 'song.ini' in low and ('notes.chart' in low or 'notes.mid' in low):
            dn[:] = []          # pasta de música não tem subpastas relevantes
            yield dp

def generated(folder):
    for ext in ('.chart', '.mid'):
        p = os.path.join(folder, 'notes.autolyrics' + ext)
        if os.path.exists(p):
            return p
    return None

def apply(folder):
    """Troca notes.X pelo notes.autolyrics.X, guardando o original como notes.X.bak (uma vez só)."""
    src = generated(folder)
    if not src:
        return False
    ext = os.path.splitext(src)[1]
    files = {f.lower(): f for f in os.listdir(folder)}
    orig = os.path.join(folder, files.get('notes' + ext, 'notes' + ext))
    bak = orig + '.bak'
    if not os.path.exists(bak):
        shutil.copy2(orig, bak)
    os.replace(src, orig)
    return True

def restore(folder):
    for ext in ('.chart', '.mid'):
        files = {f.lower(): f for f in os.listdir(folder)}
        if ('notes' + ext + '.bak') in files:
            orig = os.path.join(folder, files.get('notes' + ext, 'notes' + ext))
            os.replace(os.path.join(folder, files['notes' + ext + '.bak']), orig)
            return True
    return False

FIELDS = ['status', 'artist', 'title', 'format', 'lang', 'lyrics_source', 'lrclib_id', 'lrclib_duration_delta_s',
          'lrc_offset_s', 'lines_realigned', 'phrases', 'words', 'mean_score', 'lrc_disagree_frac', 'vocals',
          'seconds', 'applied', 'folder']

def write_csv(reports, path):
    with open(path, 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, delimiter=';')
        w.writeheader()
        for r in reports:
            q = r.get('quality', {})
            w.writerow({'status': r.get('status'), 'artist': r.get('artist'), 'title': r.get('title'),
                        'format': r.get('format'), 'lang': r.get('lang'), 'lyrics_source': r.get('lyrics_source'),
                        'lrclib_id': (r.get('lrclib') or {}).get('id'),
                        'lrclib_duration_delta_s': (r.get('lrclib') or {}).get('duration_delta_s'),
                        'lrc_offset_s': r.get('lrc_offset_s'), 'lines_realigned': r.get('lines_realigned'),
                        'phrases': r.get('phrases'), 'words': r.get('words'), 'mean_score': q.get('mean_score'),
                        'lrc_disagree_frac': q.get('lrc_disagree_frac'), 'vocals': r.get('vocals'),
                        'seconds': r.get('seconds'), 'applied': r.get('applied', False), 'folder': r.get('folder')})
