"""Busca no LRCLIB e parsing de LRC/texto em linhas de palavras."""
import re, json, os, time, unicodedata
import requests

API = 'https://lrclib.net/api'
UA = {'User-Agent': 'yarg-lyrics/0.1 (https://github.com/)'}

def _norm(s):
    s = unicodedata.normalize('NFD', s or '')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    s = re.sub(r'\(.*?\)|\[.*?\]', ' ', s)
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()

def clean_title(t):
    t = re.sub(r'\((ao vivo|live|rb3 version|.*version.*)\)', '', t, flags=re.I)
    return re.sub(r'\s+', ' ', t).strip(' .')

def clean_artist(a):
    return re.sub(r'\s*\(.*?\)', '', a).strip()

def fetch(artist, title, duration_s, cache_path=None):
    """Retorna o registro LRCLIB mais provável (dict) ou None. Prefere synced e duração próxima."""
    if cache_path and os.path.exists(cache_path):
        return json.load(open(cache_path, encoding='utf-8'))
    a, t = clean_artist(artist), clean_title(title)
    cands, answered = [], False
    for params in ({'artist_name': a, 'track_name': t}, {'q': f'{a} {t}'}):
        try:
            r = requests.get(f'{API}/search', params=params, headers=UA, timeout=20)
            if r.status_code == 429:
                time.sleep(3); r = requests.get(f'{API}/search', params=params, headers=UA, timeout=20)
            if r.ok and isinstance(r.json(), list):
                answered = True
                cands = r.json()
        except requests.RequestException:
            pass
        if cands:
            break
    def score(c):
        dd = abs((c.get('duration') or 0) - duration_s)
        same_title = _norm(c.get('trackName')) == _norm(t)
        return (0 if c.get('syncedLyrics') else 1, 0 if same_title else 1, dd)
    cands = [c for c in cands if not c.get('instrumental')]
    best = min(cands, key=score) if cands else None
    rec = None
    if best:
        rec = {k: best.get(k) for k in ('id', 'trackName', 'artistName', 'albumName', 'duration',
                                        'syncedLyrics', 'plainLyrics')}
        rec['duration_delta'] = round(abs((best.get('duration') or 0) - duration_s), 1)
    if cache_path and (answered or rec):
        json.dump(rec, open(cache_path, 'w', encoding='utf-8'), ensure_ascii=False)
    return rec

LRC_LINE = re.compile(r'^\s*((?:\[\d+:\d+(?:[.:]\d+)?\])+)(.*)$')

def parse_lrc(text):
    """Lista de linhas {'t': s|None, 'text': str}. Ignora linhas vazias e marcadores."""
    lines = []
    for raw in (text or '').splitlines():
        m = LRC_LINE.match(raw)
        if m:
            stamps = re.findall(r'\[(\d+):(\d+(?:[.:]\d+)?)\]', m.group(1))
            body = m.group(2).strip()
            for mm, ss in stamps:
                lines.append({'t': int(mm) * 60 + float(ss.replace(':', '.')), 'text': body})
        elif raw.strip() and not re.match(r'^\s*\[[a-z]+:', raw):
            lines.append({'t': None, 'text': raw.strip()})
    lines.sort(key=lambda l: (l['t'] is None, l['t'] or 0))
    out = []
    for l in lines:
        txt = re.sub(r'\[.*?\]', '', l['text']).strip()
        if txt and re.search(r'\w', txt):
            out.append({'t': l['t'], 'words': txt.split()})
    return out

def from_record(rec):
    if not rec:
        return [], None
    if rec.get('syncedLyrics'):
        return parse_lrc(rec['syncedLyrics']), 'synced'
    if rec.get('plainLyrics'):
        return parse_lrc(rec['plainLyrics']), 'plain'
    return [], None

PT_HINTS = set('que não nao de da do pra para você voce eu meu minha uma um com sem mas por ela ele é e o a os as no na'.split())
EN_HINTS = set('the you i and to my me it is in of your that on love be all we for no'.split())

def guess_lang(lines):
    words = [_norm(w) for l in lines for w in l['words']]
    pt = sum(w in PT_HINTS for w in words)
    en = sum(w in EN_HINTS for w in words)
    return 'pt' if pt >= en else 'en'
