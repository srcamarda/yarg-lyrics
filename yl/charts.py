"""Leitura/escrita de letras em notes.chart e notes.mid (padrão Clone Hero / YARG).

Modelo interno: lista de frases; cada frase = {'start': s, 'end': s, 'words': [{'t': s, 'text': str}]}
Tempos em segundos de *chart* (já descontado delay/offset do áudio).
"""
import re, os, bisect
import mido

# ---------------------------------------------------------------- tempo map
class TempoMap:
    def __init__(self, resolution, tempos):
        self.res = resolution
        if not tempos or tempos[0][0] != 0:
            tempos = [(0, 500000)] + list(tempos)
        self.ticks = [t for t, _ in tempos]
        self.uspb = [u for _, u in tempos]
        self.secs = [0.0]
        for i in range(1, len(tempos)):
            dt = self.ticks[i] - self.ticks[i - 1]
            self.secs.append(self.secs[-1] + dt / self.res * self.uspb[i - 1] / 1e6)

    def t2s(self, tick):
        i = bisect.bisect_right(self.ticks, tick) - 1
        return self.secs[i] + (tick - self.ticks[i]) / self.res * self.uspb[i] / 1e6

    def s2t(self, sec):
        sec = max(0.0, sec)
        i = max(0, bisect.bisect_right(self.secs, sec) - 1)
        return int(round(self.ticks[i] + (sec - self.secs[i]) * 1e6 / self.uspb[i] * self.res))

# ---------------------------------------------------------------- song.ini
def read_ini(folder):
    p = next((os.path.join(folder, f) for f in os.listdir(folder) if f.lower() == 'song.ini'), None)
    d = {}
    if not p:
        return d
    raw = open(p, 'rb').read()
    txt = None
    for enc in ('utf-8-sig', 'cp1252'):
        try:
            txt = raw.decode(enc); break
        except UnicodeDecodeError:
            pass
    for line in txt.splitlines():
        m = re.match(r'\s*([^=\[;]+?)\s*=\s*(.*)$', line)
        if m:
            d[m.group(1).strip().lower()] = m.group(2).strip()
    return d

# ---------------------------------------------------------------- .chart
SEC_RE = re.compile(r'\[(?P<name>[^\]]+)\]\s*\{(?P<body>.*?)\r?\n\}', re.S)

def _read_text(path):
    raw = open(path, 'rb').read()
    bom = raw.startswith(b'\xef\xbb\xbf')
    try:
        return raw.decode('utf-8-sig'), 'utf-8', bom
    except UnicodeDecodeError:
        return raw.decode('cp1252'), 'cp1252', False

class Chart:
    kind = 'chart'
    def __init__(self, path):
        self.path = path
        self.text, self.enc, self.bom = _read_text(path)
        self.nl = '\r\n' if '\r\n' in self.text else '\n'
        self.sections = {m.group('name'): m for m in SEC_RE.finditer(self.text)}
        song = self.sections['Song'].group('body')
        self.res = int(re.search(r'Resolution\s*=\s*(\d+)', song).group(1))
        mo = re.search(r'\bOffset\s*=\s*"?(-?[\d.]+)', song)
        self.offset = float(mo.group(1)) if mo else 0.0
        tempos = []
        for m in re.finditer(r'(\d+)\s*=\s*B\s+(\d+)', self.sections['SyncTrack'].group('body')):
            bpm = int(m.group(2)) / 1000.0
            tempos.append((int(m.group(1)), int(round(60e6 / bpm))))
        self.tmap = TempoMap(self.res, sorted(tempos))

    def event_lines(self):
        body = self.sections['Events'].group('body') if 'Events' in self.sections else ''
        return [l for l in body.splitlines() if l.strip()]

    def read_lyrics(self):
        lyr, phr, cur = [], [], None
        for l in self.event_lines():
            m = re.match(r'\s*(\d+)\s*=\s*E\s+"(.*)"\s*$', l)
            if not m:
                continue
            tick, ev = int(m.group(1)), m.group(2)
            if ev.startswith('lyric '):
                lyr.append((tick, ev[6:]))
            elif ev.startswith('phrase_start'):
                if cur is not None: phr.append((cur, tick))
                cur = tick
            elif ev.startswith('phrase_end') and cur is not None:
                phr.append((cur, tick)); cur = None
        return lyr, phr

    def has_lyrics(self):
        return bool(self.read_lyrics()[0])

    def write_lyrics(self, phrases, out_path):
        keep = [l for l in self.event_lines()
                if not re.search(r'=\s*E\s+"(lyric |phrase_start|phrase_end)', l)]
        new = []
        for ph in phrases:
            new.append((self.tmap.s2t(ph['start']), 0, 'phrase_start'))
            for w in ph['words']:
                txt = w['text'].replace('"', "'")
                new.append((self.tmap.s2t(w['t']), 1, f'lyric {txt}'))
            new.append((self.tmap.s2t(ph['end']), 2, 'phrase_end'))
        allev = []
        for l in keep:
            m = re.match(r'\s*(\d+)\s*=', l)
            allev.append((int(m.group(1)) if m else 0, -1, l.strip()))
        allev += [(t, o, f'{t} = E "{e}"') for t, o, e in new]
        allev.sort(key=lambda x: (x[0], x[1]))
        body = self.nl + self.nl.join('  ' + e for _, _, e in allev)
        if 'Events' in self.sections:
            m = self.sections['Events']
            out = self.text[:m.start('body')] + body + self.text[m.end('body'):]
        else:
            out = self.text.rstrip() + f'{self.nl}[Events]{self.nl}{{' + body + f'{self.nl}}}{self.nl}'
        data = out.encode(self.enc)
        if self.bom:
            data = b'\xef\xbb\xbf' + data
        open(out_path, 'wb').write(data)

# ---------------------------------------------------------------- .mid
VOCAL_TRACK = 'PART VOCALS'
PHRASE_NOTE = 105

class Midi:
    kind = 'mid'
    def __init__(self, path):
        from yl import midifix
        self.path = path
        self.mid, self.raw, self.hdr, self.vi = midifix.read(path, VOCAL_TRACK)
        tempos, abs_t = [], 0
        for msg in self.mid.tracks[0]:
            abs_t += msg.time
            if msg.type == 'set_tempo':
                tempos.append((abs_t, msg.tempo))
        self.tmap = TempoMap(self.mid.ticks_per_beat, sorted(tempos))
        self.offset = 0.0

    def _vocal(self):
        if self.vi is None or len(self.mid.tracks) < 2:
            return None
        return self.mid.tracks[1]

    def read_lyrics(self):
        tr = self._vocal()
        lyr, phr, t, open_ = [], [], 0, None
        if tr is None:
            return lyr, phr
        for m in tr:
            t += m.time
            if m.type in ('lyrics', 'text') and not m.text.startswith('['):
                lyr.append((t, m.text))
            elif m.type == 'note_on' and m.note == PHRASE_NOTE and m.velocity > 0:
                open_ = t
            elif m.type in ('note_off', 'note_on') and m.note == PHRASE_NOTE and open_ is not None:
                phr.append((open_, t)); open_ = None
        return lyr, phr

    def has_lyrics(self):
        return bool(self.read_lyrics()[0])

    def write_lyrics(self, phrases, out_path):
        """Grava cópia do MIDI original trocando só a PART VOCALS (demais trilhas byte a byte)."""
        from yl import midifix
        evs = [(0, 0, mido.MetaMessage('track_name', name=VOCAL_TRACK))]
        for ph in phrases:
            evs.append((self.tmap.s2t(ph['start']), 1, mido.Message('note_on', note=PHRASE_NOTE, velocity=100)))
            for w in ph['words']:
                evs.append((self.tmap.s2t(w['t']), 2, mido.MetaMessage('lyrics', text=w['text'])))
            evs.append((self.tmap.s2t(ph['end']), 0, mido.Message('note_off', note=PHRASE_NOTE, velocity=0)))
        evs.sort(key=lambda e: (e[0], e[1]))
        tr, last = mido.MidiTrack(), 0
        for t, _, m in evs:
            tr.append(m.copy(time=t - last)); last = t
        tr.append(mido.MetaMessage('end_of_track', time=0))
        chunk = midifix.track_bytes(tr, self.mid.ticks_per_beat)
        midifix.write(out_path, self.hdr, self.raw, self.vi, chunk)

def open_chart(folder):
    files = {f.lower(): f for f in os.listdir(folder)}
    if 'notes.chart' in files:
        return Chart(os.path.join(folder, files['notes.chart']))
    if 'notes.mid' in files:
        return Midi(os.path.join(folder, files['notes.mid']))
    raise FileNotFoundError('sem notes.chart/notes.mid')

def audio_delay(folder, chart):
    """chart_t = audio_t - delay"""
    ini = read_ini(folder)
    try:
        d = float(ini.get('delay', 0) or 0) / 1000.0
    except ValueError:
        d = 0.0
    return d + chart.offset

def lyric_events_to_words(events, tmap):
    """Junta sílabas no padrão CH ('-' continua, '=' hífen) e remove marcadores."""
    words, buf, t0 = [], '', None
    for tick, raw in events:
        s = raw.strip()
        if s in ('+', ''):
            continue
        cont = s.endswith('-') or s.endswith('=')
        s = re.sub(r'[#^*%$/§]', '', s).rstrip('-=').replace('_', ' ')
        if t0 is None:
            t0 = tmap.t2s(tick)
        buf += s
        if not cont:
            if buf.strip():
                words.append({'t': t0, 'text': buf.strip()})
            buf, t0 = '', None
    if buf.strip():
        words.append({'t': t0, 'text': buf.strip()})
    return words
