"""MIDI no nível de bytes: lê só o necessário e regrava trocando apenas a trilha PART VOCALS.

Assim trilhas de gameplay (que às vezes têm eventos malformados que o mido recusa) nunca são
re-serializadas: são copiadas byte a byte.
"""
import io, struct
import mido

def split(data):
    """(header_body, ntracks, division, [raw_chunk_bytes...]) — raw inclui 'MTrk'+tamanho."""
    assert data[:4] == b'MThd'
    hl = struct.unpack('>I', data[4:8])[0]
    hdr = data[8:8 + hl]
    i, chunks = 8 + hl, []
    while i + 8 <= len(data):
        ln = struct.unpack('>I', data[i + 4:i + 8])[0]
        chunks.append(data[i:i + 8 + ln])
        i += 8 + ln
    return hdr, chunks

def chunk_name(raw):
    """Nome da trilha (meta FF 03 nos primeiros eventos), ou ''."""
    body = raw[8:8 + 512]
    j = body.find(b'\xff\x03')
    if j < 0:
        return ''
    ln = body[j + 2]
    return body[j + 3:j + 3 + ln].decode('cp1252', 'replace').strip()

def _mini(hdr, chunks):
    fmt, _, div = struct.unpack('>HHH', hdr[:6])
    data = b'MThd' + struct.pack('>IHHH', 6, 1, len(chunks), div) + b''.join(chunks)
    return mido.MidiFile(file=io.BytesIO(data), charset='cp1252', clip=True)

def read(path, vocal_name='PART VOCALS'):
    """Retorna (MidiFile com trilha 0 + trilha de voz se houver, raw_chunks, hdr, vocal_index)."""
    data = open(path, 'rb').read()
    hdr, chunks = split(data)
    names = [chunk_name(c) for c in chunks]
    vi = next((k for k, n in enumerate(names) if n.upper() == vocal_name), None)
    want = [chunks[0]] + ([chunks[vi]] if vi not in (None, 0) else [])
    try:
        mid = _mini(hdr, want)
    except (EOFError, ValueError, KeyError, OSError):
        mid = _mini(hdr, [chunks[0]])   # trilha de voz ilegível: trata como inexistente
    return mid, chunks, hdr, vi

def track_bytes(track, ticks_per_beat):
    """Serializa uma MidiTrack do mido e devolve o chunk 'MTrk' cru."""
    f = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat, charset='cp1252')
    f.tracks.append(track)
    buf = io.BytesIO()
    f.save(file=buf)
    _, ch = split(buf.getvalue())
    return ch[0]

def write(path, hdr, chunks, vocal_index, new_chunk):
    keep = [c for k, c in enumerate(chunks) if k != vocal_index] + [new_chunk]
    fmt, _, div = struct.unpack('>HHH', hdr[:6])
    out = b'MThd' + struct.pack('>IHHH', 6, 1, len(keep), div) + b''.join(keep)
    open(path, 'wb').write(out)
