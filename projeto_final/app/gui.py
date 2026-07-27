"""
gui.py — Interface Gráfica do Tabuleiro de Xadrez Eletrônico.

Renderiza o tabuleiro de xadrez com todas as 32 peças utilizando
pygame. As peças do jogador são atualizadas com base nos eventos
dos sensores; as peças do oponente são atualizadas pela engine
ou pelo stream Lichess.

Características:
  - Renderização incremental (atualiza apenas casas alteradas)
  - Destaque do último movimento
  - Destaque dos destinos legais da peça levantada do tabuleiro
  - Barra de status com informações do jogo
  - Coordenadas nas bordas do tabuleiro
  - Peças renderizadas com caracteres Unicode de xadrez
"""

import logging
import sys
from typing import Optional

import chess

# Importação condicional do pygame (pode não estar instalado em testes)
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

from app.config import (
    BOARD_SIZE, STATUS_BAR_HEIGHT, GUI_FPS,
    LIGHT_SQUARE_COLOR, DARK_SQUARE_COLOR, HIGHLIGHT_COLOR,
    INVALID_MOVE_COLOR, BG_COLOR, STATUS_BG_COLOR, TEXT_COLOR,
    COORD_COLOR, SELECTED_SQUARE_COLOR, MOVE_HINT_COLOR, CAPTURE_HINT_COLOR,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Mapeamento de peças para caracteres Unicode
# ---------------------------------------------------------------------------

PIECE_UNICODE = {
    (chess.KING, chess.WHITE): "♔",
    (chess.QUEEN, chess.WHITE): "♕",
    (chess.ROOK, chess.WHITE): "♖",
    (chess.BISHOP, chess.WHITE): "♗",
    (chess.KNIGHT, chess.WHITE): "♘",
    (chess.PAWN, chess.WHITE): "♙",
    (chess.KING, chess.BLACK): "♚",
    (chess.QUEEN, chess.BLACK): "♛",
    (chess.ROOK, chess.BLACK): "♜",
    (chess.BISHOP, chess.BLACK): "♝",
    (chess.KNIGHT, chess.BLACK): "♞",
    (chess.PAWN, chess.BLACK): "♟",
}

# Fallback usado quando nenhuma fonte do sistema possui os glifos de xadrez.
# A cor da peça continua sendo distinguida pela cor do texto.
PIECE_ASCII = {
    (piece_type, color): letter
    for (piece_type, letter) in (
        (chess.KING, "K"), (chess.QUEEN, "Q"), (chess.ROOK, "R"),
        (chess.BISHOP, "B"), (chess.KNIGHT, "N"), (chess.PAWN, "P"),
    )
    for color in (chess.WHITE, chess.BLACK)
}

# Fontes candidatas para as peças, em ordem de preferência. Nem toda fonte
# cobre o bloco U+2654–U+265F: "arial" no Linux é resolvido para Liberation
# Sans, que não possui esses glifos e renderiza tudo como '?'.
PIECE_FONT_CANDIDATES = (
    "dejavusans",        # Linux (praticamente universal)
    "freeserif",         # Linux
    "notosanssymbols2",  # Linux/Android
    "segoeuisymbol",     # Windows
    "arialunicodems",    # Windows/macOS
    "applesymbols",      # macOS
    "dejavusansmono",
    "unifont",
)


def _find_piece_font() -> Optional[str]:
    """Procura uma fonte do sistema que contenha todos os glifos de xadrez.

    Returns:
        Caminho da fonte encontrada, ou None se nenhuma candidata cobrir
        os 12 símbolos de peça.
    """
    required = "".join(PIECE_UNICODE.values())

    for name in PIECE_FONT_CANDIDATES:
        path = pygame.font.match_font(name)
        if path is None:
            continue
        try:
            # metrics() retorna None para cada caractere ausente na fonte.
            metrics = pygame.font.Font(path, 24).metrics(required)
        except (pygame.error, OSError):
            continue
        if metrics and all(m is not None for m in metrics):
            logger.info("Fonte das peças: %s (%s)", name, path)
            return path

    logger.warning(
        "Nenhuma fonte com glifos de xadrez encontrada (tentadas: %s). "
        "Usando letras K/Q/R/B/N/P. Instale a DejaVu Sans para ver as peças.",
        ", ".join(PIECE_FONT_CANDIDATES),
    )
    return None


class ChessGUI:
    """Interface gráfica do tabuleiro de xadrez usando pygame.

    Renderiza o tabuleiro 8x8 com peças Unicode, coordenadas,
    destaque de último movimento e barra de status.
    """

    def __init__(
        self,
        board_size: int = BOARD_SIZE,
        flip_board: bool = False,
    ):
        """Inicializa a GUI.

        Args:
            board_size: Tamanho do tabuleiro em pixels.
            flip_board: Se True, renderiza com pretas embaixo.
        """
        if not PYGAME_AVAILABLE:
            raise ImportError(
                "pygame não está instalado. Instale via: pip install pygame"
            )

        self._board_size = board_size
        self._square_size = board_size // 8
        self._flip = flip_board
        self._margin = 28  # Margem para coordenadas

        # Dimensões da janela
        self._window_width = board_size + 2 * self._margin
        self._window_height = board_size + 2 * self._margin + STATUS_BAR_HEIGHT

        # Estado para renderização incremental
        self._last_board_fen: Optional[str] = None
        self._last_highlighted: Optional[set] = None
        self._last_selected: Optional[int] = None
        self._last_targets: Optional[dict[int, bool]] = None
        self._last_message: Optional[str] = None
        self._message_color = TEXT_COLOR
        self._needs_full_redraw = True

        # Pygame
        self._screen: Optional[pygame.Surface] = None
        self._clock: Optional[pygame.time.Clock] = None
        self._piece_font_path: Optional[str] = None
        self._font_pieces: Optional[pygame.font.Font] = None
        self._font_coords: Optional[pygame.font.Font] = None
        self._font_status: Optional[pygame.font.Font] = None
        self._font_message: Optional[pygame.font.Font] = None

    def start(self) -> None:
        """Inicializa o pygame e cria a janela."""
        pygame.init()
        pygame.display.set_caption("♚ Tabuleiro de Xadrez Eletrônico")

        self._screen = pygame.display.set_mode(
            (self._window_width, self._window_height)
        )
        self._clock = pygame.time.Clock()

        # Fontes
        self._piece_font_path = _find_piece_font()
        self._font_pieces = self._make_piece_font(int(self._square_size * 0.75))
        self._font_coords = pygame.font.SysFont("arial", 14)
        self._font_status = pygame.font.SysFont("arial", 16)
        self._font_message = pygame.font.SysFont("arial", 18, bold=True)

        # Desenho completo inicial
        self._screen.fill(BG_COLOR)
        self._needs_full_redraw = True

        logger.info(
            "GUI iniciada — Tabuleiro: %dx%d, Janela: %dx%d",
            self._board_size, self._board_size,
            self._window_width, self._window_height,
        )

    def _make_piece_font(self, size: int) -> "pygame.font.Font":
        """Cria uma fonte para desenhar peças no tamanho pedido."""
        if self._piece_font_path is not None:
            return pygame.font.Font(self._piece_font_path, size)
        # Fallback ASCII: letras precisam ser menores para caber na casa.
        return pygame.font.SysFont("arial", int(size * 0.8), bold=True)

    def _piece_char(self, piece: chess.Piece) -> str:
        """Retorna o símbolo a desenhar para uma peça."""
        table = PIECE_UNICODE if self._piece_font_path is not None else PIECE_ASCII
        return table[(piece.piece_type, piece.color)]

    def set_flip(self, flip: bool) -> None:
        """Define a orientação do tabuleiro (True = pretas embaixo)."""
        if flip == self._flip:
            return
        self._flip = flip
        self._needs_full_redraw = True

    def update(
        self,
        board: chess.Board,
        last_move: Optional[chess.Move] = None,
        message: str = "",
        message_type: str = "info",
        selected_square: Optional[int] = None,
        legal_targets: Optional[dict[int, bool]] = None,
    ) -> None:
        """Atualiza a renderização do tabuleiro.

        Args:
            board: Estado atual do tabuleiro (python-chess Board).
            last_move: Último movimento (para destacar casas).
            message: Mensagem para exibir na barra de status.
            message_type: Tipo da mensagem ('info', 'error', 'success').
            selected_square: Casa da peça que o jogador levantou, destacada
                enquanto ela estiver na mão.
            legal_targets: Destinos legais dessa peça, no formato
                {casa: é_captura}. Vazios recebem um ponto; capturas, um anel.
        """
        if self._screen is None:
            return

        current_fen = board.board_fen()  # Apenas posição das peças
        highlighted = set()
        if last_move:
            highlighted.add(last_move.from_square)
            highlighted.add(last_move.to_square)

        targets = legal_targets or {}

        # Verifica se precisa de redesenho completo ou incremental
        fen_changed = current_fen != self._last_board_fen
        highlight_changed = highlighted != self._last_highlighted
        selection_changed = (
            selected_square != self._last_selected or targets != self._last_targets
        )
        message_changed = message != self._last_message

        redrew_board = (
            self._needs_full_redraw
            or fen_changed or highlight_changed or selection_changed
        )
        if redrew_board:
            self._draw_full(board, highlighted, selected_square, targets)
            self._needs_full_redraw = False

        # `_draw_full` limpa a janela inteira, inclusive a barra de status:
        # ela precisa ser redesenhada junto, mesmo com a mensagem igual.
        if redrew_board or message_changed:
            self._draw_status_bar(board, message, message_type)

        # Atualiza estado para próxima comparação
        self._last_board_fen = current_fen
        self._last_highlighted = highlighted
        self._last_selected = selected_square
        self._last_targets = targets
        self._last_message = message

        pygame.display.flip()
        self._clock.tick(GUI_FPS)

    def _draw_full(
        self,
        board: chess.Board,
        highlighted: set[int],
        selected_square: Optional[int] = None,
        targets: Optional[dict[int, bool]] = None,
    ) -> None:
        """Desenha o tabuleiro completo."""
        # Fundo
        self._screen.fill(BG_COLOR)

        # Desenha casas e peças
        for rank in range(8):
            for file in range(8):
                self._draw_square(
                    board, file, rank, highlighted, selected_square, targets or {}
                )

        # Coordenadas
        self._draw_coordinates()

    def _draw_square(
        self,
        board: chess.Board,
        file: int,
        rank: int,
        highlighted: set[int],
        selected_square: Optional[int] = None,
        targets: Optional[dict[int, bool]] = None,
    ) -> None:
        """Desenha uma casa do tabuleiro com sua peça."""
        # Calcula a posição visual (considerando flip)
        if self._flip:
            visual_file = 7 - file
            visual_rank = rank
        else:
            visual_file = file
            visual_rank = 7 - rank

        x = self._margin + visual_file * self._square_size
        y = self._margin + visual_rank * self._square_size

        # Cor da casa
        is_light = (file + rank) % 2 == 0
        base_color = DARK_SQUARE_COLOR if is_light else LIGHT_SQUARE_COLOR

        # Desenha a casa
        rect = pygame.Rect(x, y, self._square_size, self._square_size)
        pygame.draw.rect(self._screen, base_color, rect)

        # Destaque do último movimento
        square = chess.square(file, rank)
        if square in highlighted:
            self._fill_square(x, y, HIGHLIGHT_COLOR)

        # Destaque da casa de onde a peça foi levantada
        if square == selected_square:
            self._fill_square(x, y, SELECTED_SQUARE_COLOR)

        # Desenha a peça
        piece = board.piece_at(square)
        if piece:
            char = self._piece_char(piece)
            # Sombra para legibilidade
            text_color = (255, 255, 255) if piece.color == chess.WHITE else (30, 30, 30)

            # Renderiza sombra
            shadow_surface = self._font_pieces.render(char, True, (0, 0, 0))
            shadow_rect = shadow_surface.get_rect(
                center=(x + self._square_size // 2 + 2, y + self._square_size // 2 + 2)
            )
            self._screen.blit(shadow_surface, shadow_rect)

            # Renderiza peça
            piece_surface = self._font_pieces.render(char, True, text_color)
            piece_rect = piece_surface.get_rect(
                center=(x + self._square_size // 2, y + self._square_size // 2)
            )
            self._screen.blit(piece_surface, piece_rect)

        # Marcador de destino legal — desenhado depois da peça, para que o
        # anel de captura envolva a peça que seria capturada.
        if targets and square in targets:
            self._draw_move_hint(x, y, targets[square])

    def _fill_square(
        self,
        x: int,
        y: int,
        color: tuple[int, int, int, int],
    ) -> None:
        """Cobre uma casa com uma cor semi-transparente."""
        overlay = pygame.Surface(
            (self._square_size, self._square_size), pygame.SRCALPHA
        )
        overlay.fill(color)
        self._screen.blit(overlay, (x, y))

    def _draw_move_hint(self, x: int, y: int, is_capture: bool) -> None:
        """Desenha o marcador de um destino legal da peça levantada.

        Segue a convenção dos tabuleiros online: ponto no centro para uma
        casa livre, anel na borda para uma captura.

        Args:
            x, y: Canto superior esquerdo da casa, em pixels.
            is_capture: True se o lance para esta casa captura uma peça.
        """
        overlay = pygame.Surface(
            (self._square_size, self._square_size), pygame.SRCALPHA
        )
        center = (self._square_size // 2, self._square_size // 2)

        if is_capture:
            width = max(3, self._square_size // 12)
            radius = self._square_size // 2 - width // 2 - 2
            pygame.draw.circle(
                overlay, CAPTURE_HINT_COLOR, center, radius, width
            )
        else:
            pygame.draw.circle(
                overlay, MOVE_HINT_COLOR, center, max(4, self._square_size // 7)
            )

        self._screen.blit(overlay, (x, y))

    def _draw_coordinates(self) -> None:
        """Desenha as coordenadas (a-h, 1-8) nas bordas do tabuleiro."""
        files_labels = "abcdefgh"
        ranks_labels = "12345678"

        for i in range(8):
            # Colunas (letras) — embaixo
            if self._flip:
                label = files_labels[7 - i]
            else:
                label = files_labels[i]

            text = self._font_coords.render(label, True, COORD_COLOR)
            x = self._margin + i * self._square_size + self._square_size // 2
            y_bottom = self._margin + self._board_size + 6
            text_rect = text.get_rect(center=(x, y_bottom))
            self._screen.blit(text, text_rect)

            # Linhas (números) — esquerda
            if self._flip:
                label = ranks_labels[i]
            else:
                label = ranks_labels[7 - i]

            text = self._font_coords.render(label, True, COORD_COLOR)
            x_left = self._margin // 2
            y = self._margin + i * self._square_size + self._square_size // 2
            text_rect = text.get_rect(center=(x_left, y))
            self._screen.blit(text, text_rect)

    def _draw_status_bar(
        self,
        board: chess.Board,
        message: str = "",
        message_type: str = "info",
    ) -> None:
        """Desenha a barra de status inferior."""
        bar_y = self._margin + self._board_size + self._margin
        bar_rect = pygame.Rect(0, bar_y, self._window_width, STATUS_BAR_HEIGHT)
        pygame.draw.rect(self._screen, STATUS_BG_COLOR, bar_rect)

        # Linha separadora
        pygame.draw.line(
            self._screen, COORD_COLOR,
            (0, bar_y), (self._window_width, bar_y), 1,
        )

        # Turno atual — indicador desenhado, para não depender de glifos
        # Unicode (U+2B1B/U+2B1C faltam na maioria das fontes de texto).
        turn_text = "Brancas" if board.turn == chess.WHITE else "Pretas"
        indicator = pygame.Rect(10, bar_y + 11, 13, 13)
        pygame.draw.rect(
            self._screen,
            (255, 255, 255) if board.turn == chess.WHITE else (30, 30, 30),
            indicator,
        )
        pygame.draw.rect(self._screen, COORD_COLOR, indicator, 1)

        turn_surface = self._font_status.render(
            f"Turno: {turn_text}", True, TEXT_COLOR
        )
        self._screen.blit(turn_surface, (31, bar_y + 8))

        # Número do movimento
        move_num = board.fullmove_number
        move_surface = self._font_status.render(
            f"Movimento: {move_num}", True, COORD_COLOR
        )
        self._screen.blit(move_surface, (10, bar_y + 32))

        # Mensagem (lado direito)
        if message:
            if message_type == "error":
                msg_color = INVALID_MOVE_COLOR
            elif message_type == "success":
                msg_color = (100, 200, 100)
            else:
                msg_color = TEXT_COLOR

            # Espaço livre até onde o texto da esquerda termina
            left_edge = max(
                31 + turn_surface.get_width(), 10 + move_surface.get_width()
            )
            available = self._window_width - 15 - left_edge - 12

            msg_surface = self._render_fitted(message, msg_color, available)
            msg_rect = msg_surface.get_rect(
                midright=(self._window_width - 15, bar_y + STATUS_BAR_HEIGHT // 2)
            )
            self._screen.blit(msg_surface, msg_rect)

    def _render_fitted(
        self,
        message: str,
        color: tuple[int, int, int],
        max_width: int,
    ) -> "pygame.Surface":
        """Renderiza a mensagem cabendo em `max_width`.

        As instruções para o jogador podem ser longas ("remova de a1, b2 e
        coloque em c3, d4"); reduz o corpo da fonte e, em último caso, corta
        o texto com reticências, para não invadir o lado esquerdo da barra.
        """
        for font in (self._font_message, self._font_status, self._font_coords):
            if font.size(message)[0] <= max_width:
                return font.render(message, True, color)

        # Reticências em ASCII: nem toda fonte do sistema tem U+2026.
        font = self._font_coords
        text = message
        while text and font.size(text + "...")[0] > max_width:
            text = text[:-1]
        return font.render(f"{text}..." if text else "", True, color)

    def show_message(self, message: str, message_type: str = "info") -> None:
        """Exibe uma mensagem temporária na barra de status.

        Args:
            message: Texto da mensagem.
            message_type: 'info', 'error' ou 'success'.
        """
        self._last_message = message
        self._message_color = (
            INVALID_MOVE_COLOR if message_type == "error"
            else (100, 200, 100) if message_type == "success"
            else TEXT_COLOR
        )

    def handle_events(self) -> bool:
        """Processa eventos do pygame.

        Returns:
            False se o usuário fechou a janela, True caso contrário.
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_f:
                    # Toggle flip board
                    self._flip = not self._flip
                    self._needs_full_redraw = True

        return True

    def show_promotion_dialog(self) -> chess.PieceType:
        """Exibe diálogo de seleção de peça para promoção.

        Returns:
            Tipo de peça selecionado (QUEEN, ROOK, BISHOP ou KNIGHT).
        """
        # Desenha overlay com opções
        overlay = pygame.Surface(
            (self._window_width, self._window_height), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 150))
        self._screen.blit(overlay, (0, 0))

        # Opções de promoção
        options = [
            (chess.QUEEN, "Dama (Q)"),
            (chess.ROOK, "Torre (R)"),
            (chess.BISHOP, "Bispo (B)"),
            (chess.KNIGHT, "Cavalo (N)"),
        ]

        # Usa a mesma fonte das peças: precisa cobrir os símbolos de xadrez.
        font = self._make_piece_font(28)
        y_start = self._window_height // 2 - 80

        for i, (piece_type, name) in enumerate(options):
            symbol = self._piece_char(chess.Piece(piece_type, chess.BLACK))
            label = f"{symbol} {name}"
            text = font.render(label, True, TEXT_COLOR)
            rect = text.get_rect(
                center=(self._window_width // 2, y_start + i * 45)
            )
            self._screen.blit(text, rect)

        pygame.display.flip()

        # Aguarda input do teclado
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return chess.QUEEN
                if event.type == pygame.KEYDOWN:
                    key_map = {
                        pygame.K_q: chess.QUEEN,
                        pygame.K_r: chess.ROOK,
                        pygame.K_b: chess.BISHOP,
                        pygame.K_n: chess.KNIGHT,
                        pygame.K_RETURN: chess.QUEEN,
                    }
                    if event.key in key_map:
                        return key_map[event.key]

    def close(self) -> None:
        """Encerra o pygame e fecha a janela."""
        if PYGAME_AVAILABLE:
            pygame.quit()
        logger.info("GUI encerrada.")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
