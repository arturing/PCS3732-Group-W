"""Roda todas as suítes de teste em sequência.

    python tests/run_all.py

Cada suíte é um script independente (sem pytest, sem dependência nova) que
sai com código 0 se tudo passou. As sondas `probe_*.py` não entram aqui:
elas falam com o Lichess de verdade e precisam de token.
"""

import subprocess
import sys
from pathlib import Path

TESTS = [
    ("Modo Lichess (cliente + aplicação)", "test_lichess.py"),
    ("Desafios diretos e recebidos", "test_challenge.py"),
    ("Loop principal (modo Stockfish)", "test_stockfish_loop.py"),
]

here = Path(__file__).resolve().parent
failed = []

for title, script in TESTS:
    print(f"\n{'=' * 70}\n  {title}  —  {script}\n{'=' * 70}")
    result = subprocess.run([sys.executable, str(here / script)])
    if result.returncode != 0:
        failed.append(script)

print(f"\n{'=' * 70}")
if failed:
    print(f"FALHARAM: {', '.join(failed)}")
    sys.exit(1)
print(f"Todas as {len(TESTS)} suítes passaram.")
