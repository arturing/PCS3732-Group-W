"""Regressão do loop principal (modo Stockfish) após a reestruturação."""

import sys
from pathlib import Path

# Permite rodar como script de dentro de tests/, sem instalar o pacote
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import threading
import time


import chess
from app.config import GameMode, PlayerColor
from app.main import ChessApplication

failures = []


def check(label, cond, extra=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label} {extra}")
    if not cond:
        failures.append(label)


class FakeIPC:
    """Entrega eventos de sensor num roteiro, com pausas entre eles."""

    def __init__(self, script):
        self.script = list(script)
        self.sent = []

    def set_process_args(self, args):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def send_to_process(self, message):
        self.sent.append(message)

    def read_event(self, timeout=0.05):
        if self.script:
            item = self.script.pop(0)
            if item is None:          # marcador de pausa
                time.sleep(timeout)
                return None
            return item
        time.sleep(timeout)
        return None


class FakeEngine:
    def __init__(self, moves, think=0.0):
        self.moves = list(moves)
        self.think = think

    def start(self):
        pass

    def stop(self):
        pass

    def get_best_move(self, board):
        time.sleep(self.think)
        return chess.Move.from_uci(self.moves.pop(0))


# Jogador: e2e4, depois e4xd5. Engine: d7d5, depois Dd8xd5 (captura o peão
# do jogador em d5 — que precisa sair fisicamente do tabuleiro).
script = [
    None, None,
    {"e2": 0}, {"e4": 1},          # e2e4
    None, None, None,
    {"e4": 0}, {"d5": 1},          # e4xd5 (peça capturada é virtual)
    None, None, None,
    {"d5": 0},                     # jogador retira o peão capturado pela dama
    None, None, None,
]

app = ChessApplication(
    mode=GameMode.STOCKFISH,
    player_color=PlayerColor.WHITE,
    no_gui=True,
)
app.ipc_reader = FakeIPC(script)
app.stockfish = FakeEngine(["d7d5", "d8d5"])

instructions = []
original = app._set_board_message


def spy(message, message_type="info"):
    if message and (not instructions or instructions[-1] != message):
        instructions.append(message)
    original(message, message_type)


app._set_board_message = spy

thread = threading.Thread(target=app.run, daemon=True)
thread.start()
time.sleep(3.0)
app._running = False
thread.join(timeout=5)

history = [m.uci() for m in app.game_state.move_history]
check("partida completa aplicada",
      history == ["e2e4", "d7d5", "e4d5", "d8d5"], history)
check("captura pelo oponente vira instrução física",
      any("remova a peça de d5" in i.lower() for i in instructions), instructions)
check("tabuleiro volta a ficar sincronizado",
      any("posição certa" in i for i in instructions), instructions[-1:])
check("nenhuma peça deslocada pendente",
      not app._misplaced and not app._in_hand)
check("espelho dos sensores bate com o esperado",
      app.physical_board_state == app.game_state.get_expected_sensor_state())

print()
if failures:
    print(f"FALHAS ({len(failures)}): " + ", ".join(failures))
    sys.exit(1)
print("Loop principal OK.")
