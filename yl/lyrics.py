"""Busca no LRCLIB e parsing de LRC/texto em linhas de palavras."""
import re, json, os, time, unicodedata
import requests

API = 'https://lrclib.net/api'
UA = {'User-Agent': 'yarg-lyrics/0.2 (https://github.com/)'}

def _norm(s):
    s = unicodedata.normalize('NFD', s or '')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    s = re.sub(r'\(.*?\)|\[.*?\]', ' ', s)
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()

# parênteses/colchetes com marcações de versão: "(Co-op)", "(Live at Brixton)", "(RB3 version)", "(Remix)"...
SUFFIX_RE = re.compile(r'\s*[\(\[][^)\]]*\b(?:co-?op|live|ao vivo|version|vers[aã]o|remaster(?:ed)?|demo|edit|'
                       r'mix|remix|cover|feat\.?|ft\.?|bonus|acoustic|ac[uú]stico|master|rerecord(?:ed)?)\b[^)\]]*[\)\]]',
                       re.I)

def clean_title(t):
    t = SUFFIX_RE.sub('', t or '')
    t = re.sub(r'\s+(?:[A-Z]\.){2}$', '', t)                 # GH3: "Suicide & Redemption J.H." / "K.H."
    t = re.sub(r'\s+-\s+(?:live|ao vivo)\b.*$', '', t, flags=re.I)
    return re.sub(r'\s+', ' ', t).strip(' .-')

def clean_artist(a):
    a = re.sub(r'\s*\(.*?\)', '', a or '')
    a = re.sub(r'\s+(?:feat\.?|ft\.?|featuring)\s.*$', '', a, flags=re.I)
    return a.strip()

def _variants(a, t):
    out = []
    def add(x, y):
        if y and (x, y) not in out:
            out.append((x, y))
    add(a, t)
    add(a, t.replace('&', 'and'))
    add(a, re.sub(r'\s+and\s+', ' & ', t, flags=re.I))
    add(a, re.sub(r'\s*\(.*?\)\s*', ' ', t).strip())
    add(a[4:] if a.lower().startswith('the ') else 'The ' + a, t)
    return out

def _search(params):
    """Lista de resultados, [] se o LRCLIB respondeu vazio, None se não respondeu (rede/limite)."""
    for i in range(4):
        try:
            r = requests.get(f'{API}/search', params=params, headers=UA, timeout=20)
        except requests.RequestException:
            time.sleep(2 * (i + 1)); continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(4 * (i + 1)); continue
        if r.ok:
            try:
                j = r.json()
            except ValueError:
                return None
            return j if isinstance(j, list) else None
        return None
    return None

def _artist_ok(cand, a):
    ca, na = set(_norm(cand.get('artistName')).split()), set(_norm(a).split()) - {'the'}
    return not na or bool(ca & na)

def fetch(artist, title, duration_s, cache_path=None):
    """Registro LRCLIB mais provável (dict), {'instrumental': True} ou None."""
    if cache_path and os.path.exists(cache_path):
        rec = json.load(open(cache_path, encoding='utf-8'))
        if rec:                       # vazio em cache é tentado de novo (a busca pode ter melhorado)
            return rec
    a, t = clean_artist(artist), clean_title(title)
    if not a and ' - ' in t:
        a, t = [x.strip() for x in t.split(' - ', 1)]
    cands, answered = [], False
    for va, vt in _variants(a, t):
        res = _search({'artist_name': va, 'track_name': vt})
        answered |= res is not None
        if res:
            cands = res; break
        time.sleep(0.3)
    if not cands:
        res = _search({'q': f'{a} {t}'})
        answered |= res is not None
        cands = [c for c in (res or []) if _artist_ok(c, a)]
    def score(c):
        dd = abs((c.get('duration') or 0) - duration_s)
        same_title = _norm(c.get('trackName')) == _norm(t)
        return (0 if c.get('syncedLyrics') else 1, 0 if same_title else 1, dd)
    vocal = [c for c in cands if not c.get('instrumental')]
    rec = None
    if vocal:
        best = min(vocal, key=score)
        rec = {k: best.get(k) for k in ('id', 'trackName', 'artistName', 'albumName', 'duration',
                                        'syncedLyrics', 'plainLyrics')}
        rec['duration_delta'] = round(abs((best.get('duration') or 0) - duration_s), 1)
    elif cands:
        rec = {'instrumental': True, 'id': cands[0].get('id'), 'duration_delta': 0}
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
