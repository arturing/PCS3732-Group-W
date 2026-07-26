"""
main.py — Ponto de entrada da aplicação de Xadrez Eletrônico.

Integra todos os módulos da camada Python:
  - IPC Reader: recebe eventos do processo C / mock
  - Motor de Estado: gerencia o jogo via python-chess
  - Interpretador de Movimentos: traduz eventos em jogadas
  - Interface UCI / Stockfish: obtém jogadas da engine
  - Cliente Lichess: joga online via Board API
  - GUI: renderiza o tabuleiro no monitor

Uso:
    python -m app.main --mode stockfish
    python -m app.main --mode lichess --token lip_xxxxx
    python -m app.main --mode stockfish --ipc subprocess
"""

import argparse
import logging
import sys
import time
from queue import Queue
from typing import Optional

import chess

from app.config import (
    GameMode, PlayerColor,
    IPC_MODE, STOCKFISH_PATH, STOCKFISH_TIME_LIMIT,
    LICHESS_TOKEN,
)
from app.ipc_reader import IPCReader
from app.game_state import GameState
from app.move_interpreter import MoveInterpreter
from app.stockfish_engine import StockfishEngine
from app.lichess_client import LichessClient
from app.gui import ChessGUI

logger = logging.getLogger(__name__)


class ChessApplication:
    """Aplicação principal do tabuleiro de xadrez eletrônico.

    Orquestra todos os módulos e implementa o loop principal do jogo.
    """

    def __init__(
        self,
        mode: GameMode = GameMode.STOCKFISH,
        player_color: PlayerColor = PlayerColor.WHITE,
        ipc_mode: str = IPC_MODE,
        stockfish_path: str = STOCKFISH_PATH,
        stockfish_time: float = STOCKFISH_TIME_LIMIT,
        lichess_token: str = LICHESS_TOKEN,
        no_gui: bool = False,
        flip_board: bool = False,
    ):
        self.mode = mode
        self.player_color = player_color
        self._player_chess_color = (
            chess.WHITE if player_color == PlayerColor.WHITE else chess.BLACK
        )

        # Módulos
        self.game_state = GameState(player_color)
        self.interpreter = MoveInterpreter()
        self.ipc_reader = IPCReader(mode=ipc_mode)

        # Engine / Lichess
        self.stockfish: Optional[StockfishEngine] = None
        self.lichess: Optional[LichessClient] = None
        self._lichess_events: Queue = Queue()

        if mode == GameMode.STOCKFISH:
            self.stockfish = StockfishEngine(
                path=stockfish_path,
                time_limit=stockfish_time,
            )
        elif mode == GameMode.LICHESS:
            self.lichess = LichessClient(token=lichess_token)

        # GUI
        self._no_gui = no_gui
        self.gui: Optional[ChessGUI] = None
        if not no_gui:
            self.gui = ChessGUI(flip_board=flip_board)

        self._running = False
        self.physical_board_state = self.game_state.get_expected_sensor_state()

    def start(self) -> None:
        """Inicializa todos os módulos."""
        logger.info("Iniciando aplicação — Modo: %s", self.mode.name)

        # GUI
        if self.gui:
            self.gui.start()
            self.gui.update(
                self.game_state.board,
                message="Inicializando...",
            )

        # Engine
        if self.stockfish:
            try:
                self.stockfish.start()
            except FileNotFoundError:
                if self.gui:
                    self.gui.update(
                        self.game_state.board,
                        message="Stockfish não encontrado!",
                        message_type="error",
                    )
                logger.error(
                    "Stockfish não encontrado. Configure CHESS_STOCKFISH_PATH."
                )
                raise

        # Lichess
        if self.lichess:
            try:
                account = self.lichess.get_account()
                username = account.get("username", "?")
                logger.info("Conectado ao Lichess como: %s", username)
                if self.gui:
                    self.gui.update(
                        self.game_state.board,
                        message=f"Lichess: {username} — Buscando partida...",
                    )
            except Exception as exc:
                logger.error("Erro ao conectar ao Lichess: %s", exc)
                raise

        # IPC
        self.ipc_reader.start()

        self._running = True

        # Atualiza GUI com estado inicial
        if self.gui:
            msg = self._get_turn_message()
            self.gui.update(self.game_state.board, message=msg)

        logger.info("Aplicação inicializada com sucesso.")

    def run(self) -> None:
        """Loop principal do jogo."""
        try:
            self.start()

            while self._running:
                # Processa eventos da GUI
                if self.gui:
                    if not self.gui.handle_events():
                        logger.info("Usuário fechou a janela.")
                        break

                # Verifica fim de jogo
                if self.game_state.is_game_over:
                    result = self.game_state.get_result()
                    if self.gui:
                        self.gui.update(
                            self.game_state.board,
                            last_move=self.game_state.last_move,
                            message=result,
                            message_type="success",
                        )
                    logger.info("Fim de jogo: %s", result)
                    # Mantém a janela aberta até o usuário fechar
                    self._wait_for_close()
                    break

                # Turno do jogador físico
                if self.game_state.is_player_turn:
                    self._handle_player_turn()
                else:
                    # Turno do oponente
                    self._handle_opponent_turn()

                # Pequena pausa para não sobrecarregar a CPU
                time.sleep(0.01)

        except KeyboardInterrupt:
            logger.info("Interrompido pelo usuário.")
        except Exception as exc:
            logger.error("Erro fatal: %s", exc, exc_info=True)
        finally:
            self.stop()

    def _handle_player_turn(self) -> None:
        """Processa o turno do jogador físico.

        Lê eventos do IPC, atualiza o estado físico dos sensores
        e compara com o tabuleiro esperado. Se a diferença for um
        movimento válido, aplica. Caso contrário, alerta dessincronia.
        """
        event = self.ipc_reader.read_event(timeout=0.05)
        if event is None:
            if self.gui:
                msg_type = "error" if "ilegal" in (self.game_state.message or "") or "dessincronizado" in (self.game_state.message or "") else ("success" if "sincronizado" in (self.game_state.message or "") else "info")
                self.gui.update(
                    self.game_state.board,
                    last_move=self.game_state.last_move,
                    message=self.game_state.message or self._get_turn_message(),
                    message_type=msg_type,
                )
            return

        logger.debug("Evento recebido do IPC: %s", event)

        # Atualiza o estado físico local com os eventos do mock/hardware
        for sq, state in event.items():
            self.physical_board_state[sq] = bool(state)

        # Compara com o estado esperado
        expected = self.game_state.get_expected_sensor_state()
        missing = [sq for sq, st in expected.items() if st and not self.physical_board_state.get(sq, False)]
        extra = [sq for sq, st in expected.items() if not st and self.physical_board_state.get(sq, False)]

        if len(missing) == 0 and len(extra) == 0:
            # Tabuleiro sincronizado novamente
            logger.info("Tabuleiro físico sincronizado.")
            self.game_state.message = "Tabuleiro sincronizado. Jogue." if "ilegal" in (self.game_state.message or "") or "dessincronizado" in (self.game_state.message or "") else ""
            if self.gui:
                self.gui.update(
                    self.game_state.board,
                    last_move=self.game_state.last_move,
                    message=self.game_state.message or self._get_turn_message(),
                    message_type="success"
                )
            return

        # Prepara a "diferença" para o interpretador
        diff = {sq: 0 for sq in missing}
        diff.update({sq: 1 for sq in extra})

        # Verifica se a diferença parece um movimento possível
        if (len(missing) == 1 and len(extra) == 1) or (len(missing) == 2 and len(extra) == 2):
            move = self.interpreter.interpret(diff, self.game_state.board)
            if move and self.game_state.apply_move(move):
                logger.info("Jogada do jogador aplicada: %s", move.uci())
                # Atualiza o expected state pra nova posição
                self.physical_board_state = self.game_state.get_expected_sensor_state()

                if self.gui:
                    self.gui.update(
                        self.game_state.board,
                        last_move=move,
                        message=self.game_state.message or self._get_turn_message(),
                        message_type="success" if self.game_state.message else "info",
                    )

                if self.lichess:
                    success = self.lichess.send_move(move.uci())
                    if not success:
                        logger.error("Lichess rejeitou a jogada: %s", move.uci())
                return
            
            # Movimento ilegal reconhecível (ex: peão pular pra trás)
            if len(missing) == 1 and len(extra) == 1:
                msg = f"Movimento ilegal! Volte a peça: {extra[0]} -> {missing[0]}"
            else:
                # Eram 2 peças faltando e 2 sobrando, mas não formaram um roque válido.
                parts = [f"Retire de {','.join(extra)}", f"Coloque em {','.join(missing)}"]
                msg = f"Movimento ilegal (Roque?). {' e '.join(parts)}"
            
            self.game_state.message = msg
            if self.gui:
                self.gui.update(self.game_state.board, last_move=self.game_state.last_move, message=msg, message_type="error")
            return

        # Se for qualquer outra quantidade (ex: só pegou peça, ou 3 peças faltando), está dessincronizado
        parts = []
        if extra:
            parts.append(f"Retire de {','.join(extra)}")
        if missing:
            parts.append(f"Coloque em {','.join(missing)}")
        
        msg = f"Dessincronizado! {' e '.join(parts)}"
        self.game_state.message = msg
        if self.gui:
            self.gui.update(self.game_state.board, last_move=self.game_state.last_move, message=msg, message_type="error")

    def _handle_opponent_turn(self) -> None:
        """Processa o turno do oponente (engine ou Lichess)."""
        if self.mode == GameMode.STOCKFISH:
            self._handle_stockfish_turn()
        elif self.mode == GameMode.LICHESS:
            self._handle_lichess_turn()

    def _handle_stockfish_turn(self) -> None:
        """Obtém e aplica a jogada do Stockfish."""
        if not self.stockfish:
            return

        if self.gui:
            self.gui.update(
                self.game_state.board,
                last_move=self.game_state.last_move,
                message="Stockfish pensando...",
            )

        try:
            move = self.stockfish.get_best_move(self.game_state.board)
            self.game_state.apply_move(move)

            logger.info("Stockfish jogou: %s", move.uci())

            # Notifica o mock sobre o movimento do oponente
            # (para que ele mantenha o tabuleiro interno sincronizado)
            self.ipc_reader.send_to_process(f"opp {move.uci()}")

            if self.gui:
                self.gui.update(
                    self.game_state.board,
                    last_move=move,
                    message=self.game_state.message or self._get_turn_message(),
                )

        except Exception as exc:
            logger.error("Erro ao obter jogada do Stockfish: %s", exc)
            if self.gui:
                self.gui.update(
                    self.game_state.board,
                    last_move=self.game_state.last_move,
                    message=f"Erro Stockfish: {exc}",
                    message_type="error",
                )

    def _handle_lichess_turn(self) -> None:
        """Recebe e aplica a jogada do oponente via Lichess."""
        # Por enquanto, verifica a fila de eventos do Lichess
        try:
            event = self._lichess_events.get(timeout=0.1)
        except Exception:
            if self.gui:
                self.gui.update(
                    self.game_state.board,
                    last_move=self.game_state.last_move,
                    message="Aguardando oponente...",
                )
            return

        if event.get("type") == "gameState":
            moves_str = event.get("moves", "")
            moves_list = moves_str.split()

            # A última jogada é do oponente
            if moves_list:
                last_move_uci = moves_list[-1]
                try:
                    move = chess.Move.from_uci(last_move_uci)
                    if move in self.game_state.board.legal_moves:
                        self.game_state.apply_move(move)

                        if self.gui:
                            self.gui.update(
                                self.game_state.board,
                                last_move=move,
                                message=self.game_state.message or self._get_turn_message(),
                            )
                except (ValueError, chess.InvalidMoveError) as exc:
                    logger.error("Jogada Lichess inválida: %s", exc)

    def _get_turn_message(self) -> str:
        """Retorna mensagem indicando de quem é o turno."""
        if self.game_state.is_player_turn:
            return "Sua vez — faça um movimento no tabuleiro"
        else:
            if self.mode == GameMode.STOCKFISH:
                return "Vez do Stockfish..."
            else:
                return "Aguardando oponente..."

    def _wait_for_close(self) -> None:
        """Aguarda o usuário fechar a janela após fim de jogo."""
        if not self.gui:
            return

        while True:
            if not self.gui.handle_events():
                break
            time.sleep(0.05)

    def stop(self) -> None:
        """Encerra todos os módulos."""
        self._running = False

        if self.ipc_reader:
            self.ipc_reader.stop()

        if self.stockfish:
            self.stockfish.stop()

        if self.lichess:
            self.lichess.close()

        if self.gui:
            self.gui.close()

        logger.info("Aplicação encerrada.")


def main() -> None:
    """Ponto de entrada principal via linha de comando."""
    parser = argparse.ArgumentParser(
        description="Tabuleiro de Xadrez Eletrônico — Camada Python",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  python -m app.main --mode stockfish
  python -m app.main --mode stockfish --stockfish-path /usr/bin/stockfish
  python -m app.main --mode stockfish --ipc subprocess --stockfish-time 2.0
  python -m app.main --mode lichess --token lip_xxxxx
  python -m app.main --mode stockfish --color black --flip
        """,
    )

    parser.add_argument(
        "--mode", choices=["stockfish", "lichess"],
        default="stockfish",
        help="Modo de jogo (padrão: stockfish).",
    )
    parser.add_argument(
        "--color", choices=["white", "black"],
        default="white",
        help="Cor das peças do jogador físico (padrão: white).",
    )
    parser.add_argument(
        "--ipc", choices=["subprocess", "stdin", "pipe"],
        default="subprocess",
        help="Modo de IPC (padrão: subprocess).",
    )
    parser.add_argument(
        "--stockfish-path", default=STOCKFISH_PATH,
        help="Caminho para o binário do Stockfish.",
    )
    parser.add_argument(
        "--stockfish-time", type=float, default=STOCKFISH_TIME_LIMIT,
        help="Tempo de cálculo do Stockfish em segundos (padrão: 1.0).",
    )
    parser.add_argument(
        "--token", default=LICHESS_TOKEN,
        help="Token OAuth2 do Lichess (modo lichess).",
    )
    parser.add_argument(
        "--flip", action="store_true",
        help="Inverte o tabuleiro (pretas embaixo).",
    )
    parser.add_argument(
        "--no-gui", action="store_true",
        help="Executa sem interface gráfica (apenas log).",
    )
    parser.add_argument(
        "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Nível de log (padrão: INFO).",
    )

    args = parser.parse_args()

    # Configuração de logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Modo de jogo
    game_mode = (
        GameMode.STOCKFISH if args.mode == "stockfish"
        else GameMode.LICHESS
    )

    # Cor do jogador
    player_color = (
        PlayerColor.WHITE if args.color == "white"
        else PlayerColor.BLACK
    )

    # Cria e executa a aplicação
    app = ChessApplication(
        mode=game_mode,
        player_color=player_color,
        ipc_mode=args.ipc,
        stockfish_path=args.stockfish_path,
        stockfish_time=args.stockfish_time,
        lichess_token=args.token,
        no_gui=args.no_gui,
        flip_board=args.flip,
    )

    app.run()


if __name__ == "__main__":
    main()
