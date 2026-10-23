"""Valida um .mid byte a byte: chunks, trilhas, eventos e a trilha PART VOCALS. Só estrutura e contagens (sem letra).

Uso: python tools/midi_check.py arquivo.mid [outro.mid ...]
"""
import sys, struct

def vlq(b, i):
    v = 0
    for _ in range(4):
        c = b[i]; i += 1
        v = (v << 7) | (c & 0x7F)
        if not c & 0x80:
            return v, i
    raise ValueError('VLQ > 4 bytes')

def check_track(data, name_hint=None):
    i, t, status, problems = 0, 0, None, []
    name, n_ev, metas, notes_on, notes_off, open_notes = None, 0, {}, 0, 0, {}
    lyr = {'count': 0, 'non_ascii': 0, 'empty': 0, 'ctrl': 0, 'max_len': 0}
    end_seen = False
    try:
        while i < len(data):
            if end_seen:
                problems.append(f'{len(data) - i} bytes depois do End of Track'); break
            d, i = vlq(data, i); t += d
            b = data[i]
            if b == 0xFF:
                typ = data[i + 1]; ln, j = vlq(data, i + 2)
                payload = data[j:j + ln]
                if j + ln > len(data):
                    problems.append(f'meta 0x{typ:02X} passa do fim da trilha'); break
                metas[typ] = metas.get(typ, 0) + 1
                if typ == 0x03 and name is None:
                    name = payload.decode('latin-1')
                if typ in (0x01, 0x05) and name == 'PART VOCALS':
                    s = payload
                    lyr['count'] += 1; lyr['max_len'] = max(lyr['max_len'], len(s))
                    if not s.strip():
                        lyr['empty'] += 1
                    if any(c > 0x7F for c in s):
                        lyr['non_ascii'] += 1
                    if any(c < 0x20 for c in s):
                        lyr['ctrl'] += 1
                if typ == 0x2F:
                    end_seen = True
                i = j + ln; status = None
            elif b in (0xF0, 0xF7):
                ln, j = vlq(data, i + 1); i = j + ln; status = None
            else:
                if b & 0x80:
                    status = b; i += 1
                elif status is None:
                    problems.append(f'byte de dados 0x{b:02X} sem status (tick {t})'); break
                hi = status & 0xF0
                nb = 1 if hi in (0xC0, 0xD0) else 2
                db = data[i:i + nb]
                if any(x & 0x80 for x in db):
                    problems.append(f'dado >127 em evento 0x{status:02X} (tick {t})')
                if hi in (0x80, 0x90) and len(db) == 2:
                    note, vel = db
                    on = hi == 0x90 and vel > 0
                    k = (status & 0x0F, note)
                    if on:
                        notes_on += 1
                        if open_notes.get(k):
                            problems.append(f'nota {note} ligada de novo sem desligar (tick {t})') if len(problems) < 8 else None
                        open_notes[k] = open_notes.get(k, 0) + 1
                    else:
                        notes_off += 1
                        if open_notes.get(k):
                            open_notes[k] -= 1
                i += nb
            n_ev += 1
    except (IndexError, ValueError) as e:
        problems.append(f'trilha truncada/inválida ({type(e).__name__}: {e}) no byte {i}')
    if not end_seen:
        problems.append('sem End of Track')
    left = sum(v for v in open_notes.values() if v)
    if left:
        problems.append(f'{left} notas sem note-off')
    return {'name': name, 'events': n_ev, 'last_tick': t, 'on': notes_on, 'off': notes_off,
            'lyrics': lyr if name == 'PART VOCALS' else None, 'problems': problems}

for path in sys.argv[1:]:
    b = open(path, 'rb').read()
    print(f'== {path.split(chr(92))[-1]}  ({len(b)} bytes)')
    if b[:4] != b'MThd':
        print('  sem cabeçalho MThd'); continue
    hl = struct.unpack('>I', b[4:8])[0]
    fmt, ntr, div = struct.unpack('>HHH', b[8:14])
    print(f'  formato {fmt}, {ntr} trilhas declaradas, resolução {div}')
    i, k = 8 + hl, 0
    while i < len(b):
        cid, ln = b[i:i + 4], struct.unpack('>I', b[i + 4:i + 8])[0] if i + 8 <= len(b) else -1
        if cid != b'MTrk':
            print(f'  chunk inesperado {cid!r} no byte {i}'); break
        if i + 8 + ln > len(b):
            print(f'  trilha {k}: tamanho declarado {ln} passa do fim do arquivo')
        r = check_track(b[i + 8:i + 8 + ln])
        flag = '  <-- ' + '; '.join(r['problems']) if r['problems'] else ''
        extra = f" letras={r['lyrics']}" if r['lyrics'] else ''
        print(f"  trilha {k:2} {str(r['name'])[:22]:22} {ln:7} bytes {r['events']:6} eventos fim={r['last_tick']}{extra}{flag}")
        i += 8 + ln; k += 1
    if k != ntr:
        print(f'  ATENÇÃO: {k} trilhas no arquivo x {ntr} no cabeçalho')
