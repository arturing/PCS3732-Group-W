"""
game_state.py — Motor de Estado do Jogo.

Gerencia o estado interno do jogo de xadrez utilizando a biblioteca
python-chess. Responsável por:
  - Manter a posição das peças e o turno atual
  - Validar e aplicar movimentos
  - Detectar fim de jogo (xeque-mate, empate, etc.)
  - Fornecer o FEN e histórico de movimentos
  - Rastrear o estado esperado dos sensores (peças do jogador físico)
"""

import logging
from typing import Optional

import chess

from app.config import PlayerColor

logger = logging.getLogger(__name__)


class GameState:
    """Motor de estado do jogo de xadrez.

    Encapsula o chess.Board e fornece métodos de alto nível para
    gerenciar o fluxo de jogo.
    """

    def __init__(self, player_color: PlayerColor = PlayerColor.WHITE):
        """Inicializa o estado do jogo.

        Args:
            player_color: Cor das peças do jogador no tabuleiro físico.
        """
        self.board = chess.Board()
        self.player_color = player_color
        self._player_chess_color = (
            chess.WHITE if player_color == PlayerColor.WHITE else chess.BLACK
        )
        self.move_history: list[chess.Move] = []
        self.last_move: Optional[chess.Move] = None
        self._message: str = ""

    def set_player_color(self, player_color: PlayerColor) -> None:
        """Redefine a cor do jogador físico.

        Necessário no modo Lichess: quem decide a cor é o servidor, e ela só
        é conhecida quando a partida começa.
        """
        self.player_color = player_color
        self._player_chess_color = (
            chess.WHITE if player_color == PlayerColor.WHITE else chess.BLACK
        )

    @property
    def fen(self) -> str:
        """Retorna a representação FEN da posição atual."""
        return self.board.fen()

    @property
    def turn(self) -> chess.Color:
        """Retorna de quem é o turno atual (chess.WHITE ou chess.BLACK)."""
        return self.board.turn

    @property
    def is_player_turn(self) -> bool:
        """Verifica se é o turno do jogador físico."""
        return self.board.turn == self._player_chess_color

    @property
    def is_game_over(self) -> bool:
        """Verifica se o jogo terminou."""
        return self.board.is_game_over()

    @property
    def message(self) -> str:
        """Mensagem de status atual."""
        return self._message

    @message.setter
    def message(self, value: str) -> None:
        self._message = value

    def get_result(self) -> str:
        """Retorna o resultado do jogo como string descritiva."""
        if not self.board.is_game_over():
            return "Em andamento"

        result = self.board.result()
        outcome = self.board.outcome()

        if outcome is None:
            return result

        if outcome.termination == chess.Termination.CHECKMATE:
            winner = "Brancas" if outcome.winner == chess.WHITE else "Pretas"
            return f"Xeque-mate! {winner} vencem. ({result})"
        elif outcome.termination == chess.Termination.STALEMATE:
            return f"Empate por afogamento. ({result})"
        elif outcome.termination == chess.Termination.INSUFFICIENT_MATERIAL:
            return f"Empate por material insuficiente. ({result})"
        elif outcome.termination == chess.Termination.THREEFOLD_REPETITION:
            return f"Empate por tripla repetição. ({result})"
        elif outcome.termination == chess.Termination.FIFTY_MOVES:
            return f"Empate por regra dos 50 movimentos. ({result})"
        else:
            return result

    def is_legal_move(self, move: chess.Move) -> bool:
        """Verifica se um movimento é legal na posição atual."""
        return move in self.board.legal_moves

    def get_legal_targets(self, square: chess.Square) -> dict[int, bool]:
        """Lista os destinos legais da peça que está em `square`.

        Usado para destacar na GUI para onde a peça levantada do tabuleiro
        pode ir.

        Args:
            square: Casa de origem (índice do python-chess).

        Returns:
            Dicionário {casa_destino: é_captura}. Vazio se não houver lance
            legal a partir dessa casa (peça do oponente, casa vazia ou peça
            cravada). Uma promoção aparece uma única vez: os quatro lances
            possíveis compartilham o mesmo destino.
        """
        targets: dict[int, bool] = {}
        for move in self.board.legal_moves:
            if move.from_square == square:
                targets[move.to_square] = self.board.is_capture(move)
        return targets

    def apply_move(self, move: chess.Move) -> bool:
        """Aplica um movimento ao tabuleiro.

        Args:
            move: Movimento a ser aplicado.

        Returns:
            True se o movimento foi aplicado com sucesso, False se ilegal.
        """
        if not self.is_legal_move(move):
            logger.warning("Tentativa de aplicar movimento ilegal: %s", move.uci())
            return False

        san = self.board.san(move)
        self.board.push(move)
        self.move_history.append(move)
        self.last_move = move
        self._message = ""

        logger.info(
            "Movimento aplicado: %s (%s) — Turno: %s",
            move.uci(), san,
            "Brancas" if self.board.turn == chess.WHITE else "Pretas",
        )

        # Verifica situações especiais após o movimento
        if self.board.is_check():
            logger.info("Xeque!")
            self._message = "Xeque!"

        if self.board.is_game_over():
            self._message = self.get_result()
            logger.info("Fim de jogo: %s", self._message)

        return True

    def get_expected_sensor_state(self) -> dict[str, bool]:
        """Calcula o estado esperado dos sensores para as peças do jogador.

        Retorna um dicionário indicando quais casas devem ter peças
        do jogador (True = ocupada, False = vazia).

        Como o tabuleiro físico contém apenas as peças de uma cor,
        este método filtra apenas as peças da cor do jogador.
        """
        sensor_state: dict[str, bool] = {}

        for rank in range(8):
            for file in range(8):
                square = chess.square(file, rank)
                square_name = chess.square_name(square)
                piece = self.board.piece_at(square)

                if piece and piece.color == self._player_chess_color:
                    sensor_state[square_name] = True
                else:
                    sensor_state[square_name] = False

        return sensor_state

    def get_move_san(self, move: chess.Move) -> str:
        """Retorna a notação SAN de um movimento (antes de aplicá-lo)."""
        try:
            return self.board.san(move)
        except (ValueError, AssertionError):
            return move.uci()

    def get_last_move_san(self) -> str:
        """Retorna a notação SAN do último movimento aplicado."""
        if not self.move_history:
            return ""

        # Desfaz o último movimento para obter o SAN
        last = self.move_history[-1]
        self.board.pop()
        san = self.board.san(last)
        self.board.push(last)
        return san

    def get_full_move_list(self) -> str:
        """Retorna o histórico completo de movimentos em formato legível.

        Exemplo: "1. e4 e5 2. Nf3 Nc6"
        """
        temp_board = chess.Board()
        parts = []
        for i, move in enumerate(self.move_history):
            if temp_board.turn == chess.WHITE:
                move_num = temp_board.fullmove_number
                parts.append(f"{move_num}.")
            parts.append(temp_board.san(move))
            temp_board.push(move)
        return " ".join(parts)

    def undo_last_move(self) -> Optional[chess.Move]:
        """Desfaz o último movimento.

        Returns:
            O movimento desfeito, ou None se não houver movimentos.
        """
        if not self.move_history:
            return None

        move = self.move_history.pop()
        self.board.pop()
        self.last_move = self.move_history[-1] if self.move_history else None

        logger.info("Movimento desfeito: %s", move.uci())
        return move

    def reset(self, fen: Optional[str] = None) -> None:
        """Reinicia o jogo.

        Args:
            fen: Posição inicial. Se None, usa a posição padrão. O modo
                Lichess passa o `initialFen` quando a partida não começa da
                posição inicial.
        """
        if fen:
            self.board.set_fen(fen)
        else:
            self.board.reset()
        self.move_history.clear()
        self.last_move = None
        self._message = ""
        logger.info("Jogo reiniciado.")
