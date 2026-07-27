"""
move_interpreter.py — Interpretação de eventos de sensores em jogadas de xadrez.

Recebe as mudanças brutas dos reed switches (quais casas mudaram de estado)
e determina qual jogada de xadrez corresponde, considerando:
  - Movimentos normais (1 origem → 1 destino)
  - Capturas (peça do oponente é virtual, não está no tabuleiro físico)
  - Roque (2 origens → 2 destinos: rei + torre), quando as quatro mudanças
    chegam num evento só
  - En passant (mesmo padrão de movimento normal, peça capturada é virtual)
  - Promoção (movimento normal + flag de promoção)

NOTA: Como as peças do oponente NÃO estão no tabuleiro físico
(são renderizadas apenas na GUI), capturas se comportam como
movimentos normais do ponto de vista dos sensores.

NOTA: na prática o jogador roca em duas etapas — o rei anda duas casas e só
depois a torre. Cada etapa chega aqui como uma mudança de 1 origem → 1
destino; quem costura as duas num lance só é o `ChessApplication`, que segura
o roque aberto pelo rei até a torre chegar. Este módulo devolve o roque a
partir do lance do rei (é assim que o python-chess o representa) e o caso de
2 origens → 2 destinos cobre o evento único que traz tudo de uma vez.
"""

import logging
from typing import Optional

import chess

logger = logging.getLogger(__name__)


class MoveInterpreter:
    """Interpreta mudanças de sensores como jogadas de xadrez.

    Trabalha em conjunto com o chess.Board para validar as jogadas
    identificadas e tratar casos especiais (roque, promoção).
    """

    def __init__(self):
        self._pending_changes: dict[str, int] = {}

    def reset(self) -> None:
        """Limpa as mudanças pendentes."""
        self._pending_changes.clear()

    def accumulate(self, changes: dict[str, int]) -> None:
        """Acumula mudanças incrementais de sensores.

        Útil quando o jogador está no meio de um movimento (levantou
        a peça mas ainda não colocou no destino).

        Args:
            changes: Dicionário {casa: estado} com as mudanças detectadas.
        """
        self._pending_changes.update(changes)

    def interpret(
        self,
        changes: dict[str, int],
        board: chess.Board,
    ) -> Optional[chess.Move]:
        """Interpreta mudanças de sensores como uma jogada de xadrez.

        Args:
            changes: Dicionário {casa: estado} com as mudanças detectadas.
                     Exemplo: {"e2": 0, "e4": 1}
            board: Estado atual do tabuleiro (python-chess Board).

        Returns:
            chess.Move se uma jogada válida foi identificada, None caso contrário.
        """
        # Classificar mudanças em origens (ficaram vazias) e destinos (ficaram
        # ocupados)
        origins: list[str] = []       # casas que ficaram vazias (peça saiu)
        destinations: list[str] = []  # casas que ficaram ocupadas (peça chegou)

        for square_name, state in changes.items():
            if state == 0:
                origins.append(square_name)
            elif state == 1:
                destinations.append(square_name)

        logger.debug(
            "Mudanças — origens (saíram): %s, destinos (chegaram): %s",
            origins, destinations,
        )

        # ------------------------------------------------------------------
        #  Caso 1: Movimento normal ou captura (1 origem, 1 destino)
        # ------------------------------------------------------------------
        if len(origins) == 1 and len(destinations) == 1:
            return self._interpret_simple_move(origins[0], destinations[0], board)

        # ------------------------------------------------------------------
        #  Caso 2: Roque (2 origens, 2 destinos)
        # ------------------------------------------------------------------
        if len(origins) == 2 and len(destinations) == 2:
            return self._interpret_castling(origins, destinations, board)

        # ------------------------------------------------------------------
        #  Caso 3: Apenas origem (peça levantada, aguardando destino)
        # ------------------------------------------------------------------
        if len(origins) >= 1 and len(destinations) == 0:
            logger.info(
                "Peça levantada de %s — aguardando destino.", origins
            )
            return None

        # ------------------------------------------------------------------
        #  Caso 4: Apenas destino (sem origem correspondente — anomalia)
        # ------------------------------------------------------------------
        if len(origins) == 0 and len(destinations) >= 1:
            logger.warning(
                "Destino(s) %s sem origem correspondente — possível "
                "reposicionamento.", destinations
            )
            return None

        # ------------------------------------------------------------------
        #  Caso inesperado
        # ------------------------------------------------------------------
        logger.warning(
            "Padrão de mudança não reconhecido — origens: %s, destinos: %s",
            origins, destinations,
        )
        return None

    def _interpret_simple_move(
        self,
        origin: str,
        destination: str,
        board: chess.Board,
    ) -> Optional[chess.Move]:
        """Interpreta um movimento simples (1 origem → 1 destino).

        Trata também promoções: se um peão chega à última fileira,
        tenta promoção para dama por padrão.
        """
        from_sq = chess.parse_square(origin)
        to_sq = chess.parse_square(destination)

        # Verifica se é promoção (peão chegando à última fileira)
        piece = board.piece_at(from_sq)
        promotion = None

        if piece and piece.piece_type == chess.PAWN:
            target_rank = chess.square_rank(to_sq)
            if (piece.color == chess.WHITE and target_rank == 7) or \
               (piece.color == chess.BLACK and target_rank == 0):
                # Promoção — padrão: Dama
                promotion = chess.QUEEN
                logger.info("Promoção detectada em %s → Dama", destination)

        move = chess.Move(from_sq, to_sq, promotion=promotion)

        # Verifica se o movimento é legal
        if move in board.legal_moves:
            logger.info("Movimento válido: %s", move.uci())
            return move

        # Se promoção falhou com Dama, tenta sem promoção (edge case)
        if promotion:
            move_no_promo = chess.Move(from_sq, to_sq)
            if move_no_promo in board.legal_moves:
                return move_no_promo

        # Tenta outras promoções
        if piece and piece.piece_type == chess.PAWN:
            target_rank = chess.square_rank(to_sq)
            if (piece.color == chess.WHITE and target_rank == 7) or \
               (piece.color == chess.BLACK and target_rank == 0):
                for promo_piece in [chess.ROOK, chess.BISHOP, chess.KNIGHT]:
                    alt_move = chess.Move(from_sq, to_sq, promotion=promo_piece)
                    if alt_move in board.legal_moves:
                        logger.info(
                            "Promoção alternativa: %s", alt_move.uci()
                        )
                        return alt_move

        logger.warning(
            "Movimento ilegal: %s → %s (UCI: %s)",
            origin, destination, move.uci(),
        )
        return None

    def _interpret_castling(
        self,
        origins: list[str],
        destinations: list[str],
        board: chess.Board,
    ) -> Optional[chess.Move]:
        """Interpreta um roque (2 origens, 2 destinos).

        No roque, o rei e a torre se movem simultaneamente:
          - O-O  (curto): rei e1→g1, torre h1→f1  (brancas)
          - O-O-O (longo): rei e1→c1, torre a1→d1  (brancas)
          - O-O  (curto): rei e8→g8, torre h8→f8  (pretas)
          - O-O-O (longo): rei e8→c8, torre a8→d8  (pretas)

        Identificamos o roque encontrando o movimento do rei entre as
        mudanças detectadas.
        """
        # Encontrar qual das origens contém o rei
        king_origin = None
        king_dest = None

        for orig in origins:
            sq = chess.parse_square(orig)
            piece = board.piece_at(sq)
            if piece and piece.piece_type == chess.KING:
                king_origin = orig
                break

        if king_origin is None:
            logger.warning("Roque detectado mas rei não encontrado nas origens: %s", origins)
            return None

        # O destino do rei é determinado pelo padrão de roque
        # Rei curto: move 2 casas para a direita (g1/g8)
        # Rei longo: move 2 casas para a esquerda (c1/c8)
        king_sq = chess.parse_square(king_origin)

        for dest in destinations:
            dest_sq = chess.parse_square(dest)
            # O destino do rei no roque é g1/g8 (curto) ou c1/c8 (longo)
            move = chess.Move(king_sq, dest_sq)
            if move in board.legal_moves:
                # Verifica se é realmente um roque (rei se move 2 casas)
                file_diff = abs(chess.square_file(dest_sq) - chess.square_file(king_sq))
                if file_diff == 2:
                    logger.info("Roque detectado: %s", move.uci())
                    return move

        logger.warning(
            "Padrão de roque não reconhecido — origens: %s, destinos: %s",
            origins, destinations,
        )
        return None


# ---------------------------------------------------------------------------
#  Instruções para o jogador
# ---------------------------------------------------------------------------

# Acima disso as casas são resumidas, para a instrução caber na barra de status
MAX_LISTED_SQUARES = 3


def _format_squares(squares: list[str]) -> str:
    """Formata uma lista de casas em ordem, resumindo se forem muitas."""
    ordered = sorted(squares)
    if len(ordered) <= MAX_LISTED_SQUARES:
        return ", ".join(ordered)
    listed = ", ".join(ordered[:MAX_LISTED_SQUARES])
    return f"{listed} e mais {len(ordered) - MAX_LISTED_SQUARES}"


def build_undo_instruction(current: str, home: str) -> str:
    """Instrução para levar uma peça deslocada de volta à casa de origem.

    Só deve ser usada quando o par origem→destino é *conhecido* (foi
    registrado quando o movimento ilegal aconteceu).
    """
    return f"mova a peça de {current} para {home}"


def build_board_instruction(missing: list[str], extra: list[str]) -> str:
    """Monta a instrução física que ressincroniza o tabuleiro.

    Traduz a diferença entre os sensores e a posição esperada em uma ordem
    no imperativo, do ponto de vista de quem está com as mãos no tabuleiro.

    IMPORTANTE: nunca emparelha uma casa vazia com uma ocupada ("mova de X
    para Y"). Os sensores só dizem *onde* há ímã, não *qual* peça é — um
    palpite errado mandaria o jogador pôr uma peça numa casa que, no
    tabuleiro virtual, é de outra, criando justamente a dessincronia que a
    instrução deveria corrigir. Para o par conhecido existe
    `build_undo_instruction`.

    Args:
        missing: Casas que deveriam ter peça mas estão vazias — o jogador
                 precisa COLOCAR uma peça nelas.
        extra: Casas ocupadas que deveriam estar vazias — o jogador precisa
               REMOVER a peça delas (ex: peça capturada pelo oponente).

    Returns:
        Instrução em minúsculas (ex: "remova a peça de e4"), para poder ser
        usada sozinha ou depois de um prefixo de causa. String vazia se não
        houver nada a corrigir.
    """
    if not missing and not extra:
        return ""

    if extra and not missing:
        alvo = "a peça" if len(extra) == 1 else "as peças"
        return f"remova {alvo} de {_format_squares(extra)}"

    if missing and not extra:
        alvo = "uma peça" if len(missing) == 1 else "peças"
        return f"coloque {alvo} em {_format_squares(missing)}"

    return (
        f"remova de {_format_squares(extra)} "
        f"e coloque em {_format_squares(missing)}"
    )


def square_name_to_index(name: str) -> tuple[int, int]:
    """Converte nome de casa (ex: 'e4') para índice (coluna, linha).

    Returns:
        Tupla (file_index, rank_index) onde file=0..7 (a..h) e rank=0..7 (1..8).
    """
    file_idx = ord(name[0]) - ord('a')
    rank_idx = int(name[1]) - 1
    return file_idx, rank_idx


def index_to_square_name(file_idx: int, rank_idx: int) -> str:
    """Converte índice (coluna, linha) para nome de casa (ex: 'e4')."""
    return chr(ord('a') + file_idx) + str(rank_idx + 1)
