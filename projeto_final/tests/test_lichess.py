"""Exercita o modo Lichess de ponta a ponta contra o servidor falso."""

import faulthandler
import logging
import sys
from pathlib import Path

# Permite rodar como script de dentro de tests/, sem instalar o pacote
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import time


from fake_lichess import STATE, serve

# Rede de segurança: se um stream travar, despeja as pilhas em vez de pendurar
faulthandler.dump_traceback_later(60, exit=True)
logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

server, url = serve()

from app.config import GameMode, PlayerColor
from app.main import ChessApplication
from app.lichess_client import LichessClient

failures = []


def check(label, cond, extra=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label} {extra}")
    if not cond:
        failures.append(label)


# ---------------------------------------------------------------------------
print("\n=== 1. LichessClient: conta, seek long-poll, streams ===")
# ---------------------------------------------------------------------------

client = LichessClient(token="faketoken123", api_url=url)
account = client.get_account()
check("get_account devolve a conta", account["username"] == "Tester")

client.start_account_stream()
client.create_seek(time_minutes=10, increment=0)

game = None
deadline = time.time() + 8
while time.time() < deadline and not game:
    game = client.wait_for_game_start(timeout=0.3)
check("seek + stream da conta entregam o gameStart", game is not None, game or "")
check("game_id capturado", client.game_id == "testgame")

events = []
client.start_game_stream(events.append)
deadline = time.time() + 5
while time.time() < deadline and not events:
    time.sleep(0.1)
check("gameFull chega no stream da partida",
      bool(events) and events[0].get("type") == "gameFull")

check("send_move aceito", client.send_move("e2e4") is True)
check("send_move recusado devolve False", client.send_move("a1a8") is False)

deadline = time.time() + 5
while time.time() < deadline and len(events) < 2:
    time.sleep(0.1)
states = [e for e in events if e.get("type") == "gameState"]
check("gameState com a resposta do oponente",
      bool(states) and states[-1]["moves"].split()[:2] == ["e2e4", "e7e5"],
      states[-1]["moves"] if states else "")

client.close()
check("close() derruba as threads",
      all(not t.is_alive() for t in client._threads) or not client._threads)


from app.lichess_client import is_board_time_control
print("\n=== 1a. Controle de tempo aceito pela Board API ===")
OBS = [(10,0,True),(10,3,True),(15,10,True),(8,0,True),(5,5,True),(0,12,True),(6,3,True),
       (5,3,False),(5,0,False),(3,0,False),(5,1,False),(1,0,False),(2,1,False),(7,0,False),(5,4,False)]
check("formula bate com os 15 casos observados na API real",
      all(is_board_time_control(t,i) is e for t,i,e in OBS))
try:
    LichessClient(token="faketoken123", api_url=url).create_seek(time_minutes=5, increment=3)
    check("create_seek recusa blitz", False)
except Exception as exc:
    check("create_seek recusa blitz", "rapido demais" in str(exc).replace("á","a"))

print("\n=== 1b. Seek recusado pelo servidor falha rapido ===")
bad = LichessClient(token="faketoken123", api_url=url)
bad.get_account()
bad.start_account_stream()
bad.create_seek(time_minutes=999, increment=0)
t0 = time.time()
while time.time() - t0 < 5 and not bad.seek_error:
    bad.wait_for_game_start(timeout=0.2)
check("seek recusado marca seek_error", bad.seek_error is not None, bad.seek_error or "")
check("falha detectada em poucos segundos", time.time() - t0 < 5)
bad.close()


# ---------------------------------------------------------------------------
print("\n=== 2. ChessApplication: eventos do Lichess -> tabuleiro virtual ===")
# ---------------------------------------------------------------------------

app = ChessApplication(
    mode=GameMode.LICHESS,
    player_color=PlayerColor.WHITE,
    lichess_token="fake",
    no_gui=True,
)
app._lichess_user_id = "tester"

app._handle_lichess_event({
    "type": "gameFull",
    "initialFen": "startpos",
    "white": {"id": "tester", "name": "Tester"},
    "black": {"aiLevel": 3},
    "state": {"type": "gameState", "moves": "", "status": "started"},
})
check("cor resolvida como brancas", app.player_color == PlayerColor.WHITE)
check("oponente identificado como IA",
      app._opponent_name == "IA do Lichess (nível 3)", app._opponent_name)
check("GUI orientada para as brancas", app._orientation_flip() is False)

app._handle_lichess_event({
    "type": "gameState", "moves": "e2e4 e7e5", "status": "started",
})
check("dois lances aplicados", len(app.game_state.move_history) == 2)
check("vez do jogador de novo", app.game_state.is_player_turn is True)

# Idempotência: o mesmo estado reenviado não pode duplicar lances
app._handle_lichess_event({
    "type": "gameState", "moves": "e2e4 e7e5", "status": "started",
})
check("reenvio do mesmo estado é ignorado", len(app.game_state.move_history) == 2)

app._handle_lichess_event({
    "type": "gameState", "moves": "e2e4 e7e5 g1f3 b8c6", "status": "started",
})
check("lances incrementais aplicados", len(app.game_state.move_history) == 4)

app._handle_lichess_event({
    "type": "gameState", "moves": "e2e4 e7e5 g1f3 b8c6",
    "status": "resign", "winner": "white",
})
check("fim de partida por desistência",
      app._end_reason == "Desistência — você venceu!", app._end_reason)


# ---------------------------------------------------------------------------
print("\n=== 3. Cor atribuída pelo servidor difere de --color ===")
# ---------------------------------------------------------------------------

app2 = ChessApplication(
    mode=GameMode.LICHESS,
    player_color=PlayerColor.WHITE,   # pediu brancas...
    lichess_token="fake",
    no_gui=True,
)
app2._lichess_user_id = "tester"
app2._handle_lichess_event({
    "type": "gameFull",
    "white": {"id": "adversario", "name": "Adversario", "rating": 1700},
    "black": {"id": "tester", "name": "Tester"},   # ...recebeu pretas
    "state": {"type": "gameState", "moves": "", "status": "started"},
})
check("cor corrigida para pretas", app2.player_color == PlayerColor.BLACK)
check("GameState acompanhou a cor", app2.game_state.is_player_turn is False)
check("sensores esperados nas fileiras 7 e 8",
      app2.physical_board_state["a8"] and app2.physical_board_state["e7"]
      and not app2.physical_board_state["a1"])
check("GUI vira para as pretas", app2._orientation_flip() is True)
check("mock recebe --color black",
      app2._hardware_process_args() == ["--color", "black", "--flip"],
      app2._hardware_process_args())
check("oponente identificado com rating",
      app2._opponent_name == "Adversario (1700)", app2._opponent_name)

app2._handle_lichess_event({
    "type": "gameState", "moves": "d2d4", "status": "started",
})
check("lance das brancas aplicado, vez das pretas",
      app2.game_state.is_player_turn is True)


# ---------------------------------------------------------------------------
print("\n=== 4. Lance físico -> envio ao Lichess ===")
# ---------------------------------------------------------------------------

sent = []


class StubLichess:
    game_id = "testgame"
    player_color = "white"

    def send_move(self, uci):
        sent.append(uci)
        return uci != "g1f3"   # o servidor recusa este

    def close(self):
        pass


app3 = ChessApplication(
    mode=GameMode.LICHESS, player_color=PlayerColor.WHITE,
    lichess_token="fake", no_gui=True,
)
app3.lichess = StubLichess()

# Jogador levanta o peão de e2 e solta em e4
app3._apply_sensor_event({"e2": 0})
app3._apply_sensor_event({"e4": 1})
check("lance físico enviado ao Lichess", sent == ["e2e4"], sent)
check("lance aplicado localmente",
      app3.game_state.board.move_stack[-1].uci() == "e2e4")

# Oponente responde
app3._handle_lichess_event({
    "type": "gameState", "moves": "e2e4 e7e5", "status": "started",
})

# Lance recusado pelo servidor: o estado local NÃO pode avançar
app3._apply_sensor_event({"g1": 0})
app3._apply_sensor_event({"f3": 1})
check("lance recusado foi enviado", sent == ["e2e4", "g1f3"], sent)
check("lance recusado não entra no tabuleiro virtual",
      len(app3.game_state.move_history) == 2, app3.game_state.move_history)
app3._update_board_instruction()
check("jogador é instruído a desfazer",
      "f3" in app3._board_message and "g1" in app3._board_message,
      repr(app3._board_message))

# Jogador desfaz: leva a peça de f3 de volta para g1
app3._apply_sensor_event({"f3": 0})
app3._apply_sensor_event({"g1": 1})
app3._update_board_instruction()
check("tabuleiro volta a ficar limpo",
      not app3._misplaced and not app3._in_hand
      and "posição certa" in app3._board_message, repr(app3._board_message))


print()
if failures:
    print(f"FALHAS ({len(failures)}): " + ", ".join(failures))
    sys.exit(1)
print("Todos os cenários passaram.")
