"""Descobre qual corpo o /api/board/seek do Lichess aceita.

Cada tentativa abre a conexão e a fecha imediatamente — e fechar a conexão
CANCELA o seek, então nada fica publicado. Todas as tentativas são casuais
(rated=false), nunca ranqueadas.

Uso (da pasta projeto_final/):
    python /caminho/para/probe_seek.py
"""

import sys
from pathlib import Path

# Permite rodar como script de dentro de tests/, sem instalar o pacote
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


import requests
from app.config import LICHESS_TOKEN, LICHESS_TOKEN_ORIGIN, LICHESS_API_URL

if not LICHESS_TOKEN:
    sys.exit("Nenhum token encontrado. Grave-o em .lichess_token primeiro.")

print(f"Token lido de: {LICHESS_TOKEN_ORIGIN}")
print(f"API: {LICHESS_API_URL}\n")

session = requests.Session()
session.headers.update({"Authorization": f"Bearer {LICHESS_TOKEN}"})

# Cada caso: (rótulo, corpo do POST)
CASES = [
    ("atual: time+increment+rated",      {"rated": "false", "time": "5", "increment": "3"}),
    ("sem rated",                        {"time": "5", "increment": "3"}),
    ("rated booleano cru",               {"rated": False, "time": 5, "increment": 3}),
    ("com variant=standard",             {"rated": "false", "time": "5", "increment": "3",
                                          "variant": "standard"}),
    ("time como float",                  {"rated": "false", "time": "5.0", "increment": "3"}),
    ("10+0 (padrão do app)",             {"rated": "false", "time": "10", "increment": "0"}),
    ("com color=random",                 {"rated": "false", "time": "5", "increment": "3",
                                          "color": "random"}),
    ("com ratingRange vazio",            {"rated": "false", "time": "5", "increment": "3",
                                          "ratingRange": ""}),
    ("correspondência (days=1)",         {"rated": "false", "days": "1"}),
]

print(f"{'caso':<32} {'HTTP':<6} resposta")
print("-" * 88)

for label, body in CASES:
    try:
        response = session.post(
            f"{LICHESS_API_URL}/api/board/seek",
            data=body,
            headers={"Accept": "application/x-ndjson"},
            stream=True,
            timeout=(10, 5),
        )
        status = response.status_code
        detail = "" if status == 200 else response.text[:70].replace("\n", " ")
        response.close()          # fecha já: cancela o seek
    except requests.RequestException as exc:
        status, detail = "ERRO", str(exc)[:70]

    marker = "  <-- ACEITO" if status == 200 else ""
    print(f"{label:<32} {status:<6} {detail}{marker}")

session.close()
print("\nTodos os seeks foram cancelados ao fechar a conexão.")
