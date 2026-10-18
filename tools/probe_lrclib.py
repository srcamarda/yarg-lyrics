"""Testa variações de busca no LRCLIB para músicas 'sem letra'. Só metadados (id, nome, duração, synced)."""
import requests, sys, time
Q = [("DragonForce", "Through the Fire and Flames"), ("Metallica", "One"), ("Motörhead", "Motörhead"),
     ("Sex Pistols", "Problems"), ("Tenacious D", "The Metal"), ("The Smashing Pumpkins", "Cherub Rock"),
     ("Velvet Revolver", "Messages"), ("Scouts of St. Sebastian", "In Love"), ("L.A. Slum Lords", "Down N' Dirty")]
for a, t in Q:
    r = requests.get('https://lrclib.net/api/search', params={'artist_name': a, 'track_name': t}, timeout=20).json()
    time.sleep(1.5)
    r = r if isinstance(r, list) else []
    syn = [x for x in r if x.get('syncedLyrics')]
    b = (syn or r or [None])[0]
    print(f"{a} - {t}: hits={len(r)} synced={len(syn)}" + (f" | {b['artistName']} - {b['trackName']} {b['duration']:.0f}s inst={b['instrumental']}" if b else ''))
