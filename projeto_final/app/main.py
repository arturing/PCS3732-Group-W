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
from typing import NamedTuple, Optional

import chess

from app.config import (
    GameMode, PlayerColor,
    IPC_MODE, STOCKFISH_PATH, STOCKFISH_TIME_LIMIT,
    LICHESS_TOKEN,
)
from app.ipc_reader import IPCReader
from app.game_state import GameState
from app.move_interpreter import (
    MoveInterpreter, build_board_instruction, build_undo_instruction,
)
from app.stockfish_engine import StockfishEngine
from app.lichess_client import LichessClient
from app.gui import ChessGUI

logger = logging.getLogger(__name__)

# Motivos pelos quais uma peça está fora de lugar — definem a instrução exibida
REASON_ILLEGAL = "ilegal"      # o lance foi recusado pelas regras do xadrez
REASON_BLOCKED = "bloqueado"   # o lance foi feito com o tabuleiro fora da posição


class MisplacedPiece(NamedTuple):
    """Peça física fora do lugar, à espera de ser devolvida.

    O par (casa atual → `home`) é registrado no momento em que o lance foi
    recusado, então a instrução de desfazer é exata: não depende de adivinhar
    qual peça vazia corresponde a qual peça sobrando.
    """

    home: str     # casa onde a peça deveria estar
    reason: str   # REASON_ILLEGAL ou REASON_BLOCKED


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

        # Instrução física corrente ("remova a peça de e4", ...) e sua
        # severidade. Vazia quando o tabuleiro está sincronizado.
        self._board_message = ""
        self._board_message_type = "info"

        # Histórico de peças fora do lugar: {casa_atual: MisplacedPiece}.
        # Enquanto não estiver vazio, novos lances são bloqueados. A ordem de
        # inserção define a ordem de desfazer: a mais recente primeiro.
        self._misplaced: dict[str, MisplacedPiece] = {}

        # Peças deslocadas que estão na mão do jogador (levantadas do
        # tabuleiro, ainda não recolocadas).
        self._in_hand: list[MisplacedPiece] = []

    def start(self) -> None:
        """Inicializa todos os módulos."""
        logger.info("Iniciando aplicação — Modo: %s", self.mode.name)

        # GUI
        if self.gui:
            self.gui.start()
            self._refresh_gui("Inicializando...")

        # Engine
        if self.stockfish:
            try:
                self.stockfish.start()
            except FileNotFoundError:
                self._refresh_gui("Stockfish não encontrado!", "error")
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
                self._refresh_gui(f"Lichess: {username} — Buscando partida...")
            except Exception as exc:
                logger.error("Erro ao conectar ao Lichess: %s", exc)
                raise

        # IPC
        self.ipc_reader.start()

        self._running = True

        # Atualiza GUI com estado inicial
        self._refresh_gui()

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
                    self._refresh_gui(result, "success")
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
        movimento válido, aplica. Caso contrário, exibe a instrução
        do que fazer no tabuleiro para voltar à posição esperada.
        """
        event = self.ipc_reader.read_event(timeout=0.05)
        if event is not None:
            logger.debug("Evento recebido do IPC: %s", event)
            self._apply_sensor_event(event)

        # A instrução é sempre derivada do estado atual — assim ela aparece
        # também sem evento novo (ex: peça capturada pelo oponente, que o
        # jogador precisa retirar assim que o turno vira).
        self._update_board_instruction()
        self._refresh_gui()

    def _apply_sensor_event(self, event: dict[str, int]) -> None:
        """Atualiza o espelho dos sensores e reage à mudança.

        As saídas de peça são processadas antes das entradas, para que um
        evento único que já traga origem e destino (uma varredura do
        hardware pode trazer os dois) seja lido como um movimento.
        """
        lifted = [sq for sq, state in event.items() if not state]
        placed = [sq for sq, state in event.items() if state]
        move_candidate = False

        for square in lifted:
            if not self.physical_board_state.get(square, False):
                continue
            self.physical_board_state[square] = False
            if square in self._misplaced:
                # Levantou uma peça deslocada: pode estar desfazendo o lance
                self._in_hand.append(self._misplaced.pop(square))
                logger.info("Peça deslocada de %s levantada.", square)

        for square in placed:
            if self.physical_board_state.get(square, False):
                continue
            self.physical_board_state[square] = True
            if self._in_hand:
                self._place_misplaced_piece(square)
            else:
                move_candidate = True

        if move_candidate:
            self._try_apply_move()

    def _place_misplaced_piece(self, square: str) -> None:
        """Registra onde o jogador soltou a peça deslocada que tinha na mão."""
        entry = self._in_hand.pop(0)
        if square == entry.home:
            logger.info("Peça devolvida para %s.", entry.home)
            return
        # Continua fora de lugar, agora em outra casa: o registro é atualizado
        # em vez de virar uma segunda peça a devolver.
        self._misplaced[square] = entry
        logger.info(
            "Peça de %s continua deslocada (agora em %s).", entry.home, square
        )

    def _try_apply_move(self) -> None:
        """Tenta ler a diferença atual como uma jogada e aplicá-la.

        Com o tabuleiro fora da posição, nenhum lance novo é aceito: a peça
        movida entra no histórico para ser devolvida junto com as outras.
        """
        missing, extra = self._board_diff()
        if (len(missing), len(extra)) not in ((1, 1), (2, 2)):
            return

        # O par só é inequívoco com uma casa esvaziada e uma ocupada; com duas
        # de cada (tentativa de roque) não há como saber qual peça foi para
        # onde, então nada é registrado e a instrução sai da diferença mesmo.
        pair = (missing[0], extra[0]) if len(missing) == 1 == len(extra) else None

        if self._misplaced or self._in_hand:
            logger.info(
                "Lance bloqueado: o tabuleiro precisa voltar à posição antes."
            )
            if pair:
                self._remember_misplaced(*pair, REASON_BLOCKED)
            return

        diff = {sq: 0 for sq in missing}
        diff.update({sq: 1 for sq in extra})

        move = self.interpreter.interpret(diff, self.game_state.board)
        if move and self.game_state.apply_move(move):
            logger.info("Jogada do jogador aplicada: %s", move.uci())
            self._sync_mirror_to_board()
            self._set_board_message("", "info")

            if self.lichess:
                if not self.lichess.send_move(move.uci()):
                    logger.error("Lichess rejeitou a jogada: %s", move.uci())
            return

        # Lance recusado pelas regras: entra no histórico para ser desfeito.
        if pair:
            self._remember_misplaced(*pair, REASON_ILLEGAL)

    def _remember_misplaced(self, home: str, current: str, reason: str) -> None:
        """Registra uma peça fora do lugar, a ser devolvida de `current` a `home`."""
        self._misplaced[current] = MisplacedPiece(home, reason)
        logger.info(
            "Peça deslocada registrada (%s): devolver de %s para %s",
            reason, current, home,
        )

    def _sync_mirror_to_board(self) -> None:
        """Alinha o espelho dos sensores com a posição virtual.

        Necessário porque um lance mexe em casas que o jogador ainda não
        tocou fisicamente (a torre do roque, a peça capturada). As casas de
        movimentos ilegais pendentes ficam de fora: nelas o espelho precisa
        continuar refletindo o sensor real, senão o desfazer não é detectado.
        """
        pending = self._pending_squares()
        for square, occupied in self.game_state.get_expected_sensor_state().items():
            if square not in pending:
                self.physical_board_state[square] = occupied

    def _pending_squares(self) -> set[str]:
        """Casas cujo estado é explicado por uma peça deslocada pendente."""
        pending = set(self._misplaced)
        pending.update(entry.home for entry in self._misplaced.values())
        pending.update(entry.home for entry in self._in_hand)
        return pending

    def _prune_misplaced(self) -> None:
        """Descarta registros que não têm mais para onde voltar.

        Dois casos: o oponente capturou a peça deslocada (não existe mais casa
        de origem) ou o jogador já pôs outra peça na casa certa. Nos dois, o
        que resta é tirar a peça do tabuleiro — e isso a diferença normal já
        pede ("remova a peça de e5").
        """
        expected = self.game_state.get_expected_sensor_state()

        def has_home(entry: MisplacedPiece) -> bool:
            if not expected.get(entry.home, False):
                logger.info("Peça de %s foi capturada — só resta retirá-la.", entry.home)
                return False
            if self.physical_board_state.get(entry.home, False):
                logger.info("Casa %s já está ocupada — só resta retirar a peça.", entry.home)
                return False
            return True

        self._misplaced = {
            current: entry for current, entry in self._misplaced.items()
            if has_home(entry)
        }
        self._in_hand = [entry for entry in self._in_hand if has_home(entry)]

    def _board_diff(self) -> tuple[list[str], list[str]]:
        """Compara os sensores com a posição esperada.

        As casas de movimentos ilegais pendentes são ignoradas: o estado
        delas já é conhecido e tem instrução própria. Sem isso, um lance
        feito depois de um movimento ilegal apareceria misturado com ele.

        Returns:
            Tupla (missing, extra): casas que precisam receber uma peça e
            casas que precisam ser esvaziadas.
        """
        expected = self.game_state.get_expected_sensor_state()
        pending = self._pending_squares()
        missing = [
            sq for sq, occupied in expected.items()
            if occupied and sq not in pending
            and not self.physical_board_state.get(sq, False)
        ]
        extra = [
            sq for sq, occupied in expected.items()
            if not occupied and sq not in pending
            and self.physical_board_state.get(sq, False)
        ]
        return missing, extra

    def _instruction(self, reason: str, missing: list[str], extra: list[str]) -> str:
        """Compõe "<causa> — <instrução>" a partir da diferença nos sensores."""
        instruction = build_board_instruction(missing, extra)
        if not instruction:
            return reason
        if not reason:
            return instruction[0].upper() + instruction[1:]
        return f"{reason} — {instruction}"

    def _update_board_instruction(self) -> None:
        """Deriva a instrução física do estado atual dos sensores.

        Uma instrução por vez, na ordem do que o jogador precisa fazer agora:
        a peça que está na mão, as peças deslocadas (que bloqueiam o jogo) e
        depois a diferença nos sensores.
        """
        # Havia algo pendente? Um lance aplicado limpa a mensagem antes de
        # chegar aqui, então isto distingue "acabei de arrumar o tabuleiro"
        # de "acabei de jogar".
        had_pending = bool(self._board_message)
        self._prune_misplaced()
        missing, extra = self._board_diff()

        # 1. Peça deslocada na mão: falta recolocá-la na casa de origem
        if self._in_hand:
            entry = self._in_hand[0]
            self._set_board_message(
                f"{self._undo_reason(entry)} — coloque a peça em {entry.home}",
                "error",
            )
            return

        # 2. Peças deslocadas: até devolvê-las, nenhum lance novo é aceito.
        #    Desfaz da mais recente para a mais antiga, que é a ordem em que
        #    foram deslocadas (a mais nova pode estar na casa da mais velha).
        if self._misplaced:
            current, entry = next(reversed(self._misplaced.items()))
            self._set_board_message(
                f"{self._undo_reason(entry)} — "
                f"{build_undo_instruction(current, entry.home)}",
                "error",
            )
            return

        # 3. Peça levantada para jogar: movimento em andamento, não é erro
        if not extra and len(missing) == 1:
            self._set_board_message(
                f"Peça de {missing[0]} na mão — solte no destino", "info"
            )
            return

        # 4. Outras diferenças nos sensores
        if missing or extra:
            if missing and extra:
                # Bagunça de verdade: pede a correção casa por casa
                self._set_board_message(
                    self._instruction("Tabuleiro fora de sincronia", missing, extra),
                    "error",
                )
            else:
                # Só remoções é o caso normal depois de uma captura do
                # oponente (ação pendente, não erro).
                severity = "error" if missing else "info"
                self._set_board_message(
                    self._instruction("", missing, extra), severity
                )
            return

        # 5. Tudo no lugar. A confirmação se auto-sustenta (had_pending
        #    continua verdadeiro nos ciclos seguintes), ficando em cartaz até
        #    o próximo lance ou problema.
        if had_pending:
            self._set_board_message("Tabuleiro na posição certa — sua vez", "success")
        else:
            self._set_board_message("", "info")

    def _undo_reason(self, entry: MisplacedPiece) -> str:
        """Prefixo que explica por que a peça precisa voltar para a casa dela."""
        reason = (
            "Desfaça o movimento ilegal" if entry.reason == REASON_ILLEGAL
            else "Arrume o tabuleiro antes de jogar"
        )
        pending = len(self._misplaced) + len(self._in_hand)
        return f"{reason} ({pending} pendentes)" if pending > 1 else reason

    def _set_board_message(self, message: str, message_type: str = "info") -> None:
        """Define a instrução exibida na barra de status."""
        if message and message != self._board_message:
            # Também registrada no log: é a única saída no modo --no-gui
            logger.info("Instrução ao jogador: %s", message)
        self._board_message = message
        self._board_message_type = message_type

    def _current_status(self) -> tuple[str, str]:
        """Mensagem que a barra de status deve exibir e sua severidade.

        A instrução física tem prioridade: enquanto o tabuleiro não estiver
        na posição esperada, é ela que o jogador precisa ler. Avisos do jogo
        ("Xeque!") entram como prefixo para não se perderem.
        """
        if self._board_message:
            if self.game_state.message:
                return (
                    f"{self.game_state.message} {self._board_message}",
                    self._board_message_type,
                )
            return self._board_message, self._board_message_type
        if self.game_state.message:
            return self.game_state.message, "info"
        return self._get_turn_message(), "info"

    def _refresh_gui(
        self,
        message: Optional[str] = None,
        message_type: str = "info",
    ) -> None:
        """Redesenha a GUI.

        Args:
            message: Texto a exibir. Se None, usa a instrução/status corrente.
            message_type: Severidade quando `message` é informado.
        """
        if not self.gui:
            return
        if message is None:
            message, message_type = self._current_status()
        self.gui.update(
            self.game_state.board,
            last_move=self.game_state.last_move,
            message=message,
            message_type=message_type,
        )

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

        self._refresh_gui("Stockfish pensando...")

        try:
            move = self.stockfish.get_best_move(self.game_state.board)
            self.game_state.apply_move(move)

            logger.info("Stockfish jogou: %s", move.uci())

            # Notifica o mock sobre o movimento do oponente
            # (para que ele mantenha o tabuleiro interno sincronizado)
            self.ipc_reader.send_to_process(f"opp {move.uci()}")

            # A jogada do oponente pode exigir ação física do jogador —
            # tirar do tabuleiro a peça que acabou de ser capturada.
            self._update_board_instruction()
            self._refresh_gui()

        except Exception as exc:
            logger.error("Erro ao obter jogada do Stockfish: %s", exc)
            self._refresh_gui(f"Erro Stockfish: {exc}", "error")

    def _handle_lichess_turn(self) -> None:
        """Recebe e aplica a jogada do oponente via Lichess."""
        # Por enquanto, verifica a fila de eventos do Lichess
        try:
            event = self._lichess_events.get(timeout=0.1)
        except Exception:
            self._refresh_gui("Aguardando oponente...")
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

                        # Pode ter capturado uma peça do jogador
                        self._update_board_instruction()
                        self._refresh_gui()
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
