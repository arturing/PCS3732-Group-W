"""Desafio direto e aceite automático de desafios recebidos."""

import logging
import sys
import time
from pathlib import Path

# Permite rodar como script de dentro de tests/, sem instalar o pacote
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fake_lichess import STATE, serve

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

server, url = serve()

from app.lichess_client import LichessClient, LichessError

failures = []


def check(label, cond, extra=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label} {extra}")
    if not cond: failures.append(label)

print("\n=== Desafio direto a outra conta ===")
c = LichessClient(token="faketoken123", api_url=url)
c.get_account()
ch = c.create_challenge("adversario", time_minutes=10, increment=0, color="white")
check("desafio criado com id e url", ch.get("id") == "testgame" and "url" in ch, ch)

c.start_account_stream()
game = None
t0 = time.time()
while time.time() - t0 < 8 and not game:
    game = c.wait_for_game_start(timeout=0.3)
check("gameStart recebido apos o desafio", game is not None)
check("desafio proprio (direction=out) NAO foi aceito",
      "outgoing1" not in STATE.accepted, STATE.accepted)
check("desafio recebido (direction=in) foi aceito",
      "incoming1" in STATE.accepted, STATE.accepted)
check("desafio pendente limpo apos gameStart", c._pending_challenge_id is None)
c.close()
check("nada cancelado (o desafio virou partida)", STATE.cancelled == [], STATE.cancelled)

print("\n=== Desafio nao aceito e cancelado no encerramento ===")
STATE.accepted.clear(); STATE.cancelled.clear()
c2 = LichessClient(token="faketoken123", api_url=url)
c2.get_account()
c2.create_challenge("adversario", time_minutes=10, increment=0)
c2.close()
check("desafio pendente cancelado no close()",
      STATE.cancelled == ["testgame"], STATE.cancelled)

print("\n=== Usuario inexistente ===")
c3 = LichessClient(token="faketoken123", api_url=url)
try:
    c3.create_challenge("naoexiste", time_minutes=10, increment=0)
    check("usuario inexistente vira erro claro", False)
except LichessError as exc:
    check("usuario inexistente vira erro claro", "não existe" in str(exc), str(exc))
c3.close()

print()
if failures:
    print(f"FALHAS ({len(failures)}): " + ", ".join(failures)); sys.exit(1)
print("Desafios OK.")
