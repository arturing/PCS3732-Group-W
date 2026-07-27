"""Qual combinação (time, increment) o /api/board/seek aceita?"""
import sys, time as _t
import requests
from app.config import LICHESS_TOKEN, LICHESS_API_URL

s = requests.Session()
s.headers.update({"Authorization": f"Bearer {LICHESS_TOKEN}"})

COMBOS = [(8,0),(7,0),(5,5),(5,4),(0,12),(6,3)]
print(f"{'time+inc':<12} {'HTTP':<6} detalhe")
print("-"*70)
for t, inc in COMBOS:
    try:
        r = s.post(f"{LICHESS_API_URL}/api/board/seek",
                   data={"rated": "false", "time": str(t), "increment": str(inc)},
                   headers={"Accept": "application/x-ndjson"},
                   stream=True, timeout=(10, 5))
        st = r.status_code
        d = "ACEITO" if st == 200 else r.text[:55].replace("\n"," ")
        r.close()
    except requests.RequestException as e:
        st, d = "ERRO", str(e)[:55]
    print(f"{t}+{inc:<10} {st:<6} {d}")
    _t.sleep(1.0)
s.close()
