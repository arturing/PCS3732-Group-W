"""
gui_mock.py — Interface gráfica do mock de hardware (matriz de botões 8×8).

Cada casa do tabuleiro é um botão que representa um reed switch:

  - PRESSIONADO (afundado, LED verde) → sensor ativo (ímã/peça detectada)
  - SOLTO (em relevo)                 → sensor inativo (casa vazia)

Clicar numa casa alterna o sensor e emite imediatamente o evento IPC
correspondente, exatamente como faria a varredura da matriz real. Arrastar
o mouse com o botão pressionado "pinta" as casas com o mesmo estado do
primeiro clique — útil para montar uma posição rapidamente.

Este módulo é BURRO como o resto do mock: não conhece regras de xadrez,
turnos ou movimentos legais — apenas liga e desliga sensores.

Não depende de `hardware_mock` (nem do pacote `app`): recebe o grid de
sensores e o callback de envio por parâmetro, para poder ser executado
tanto como módulo (`python -m mock.hardware_mock`) quanto como script.
"""

import logging
import os
from typing import Callable, Optional, Protocol

# O banner de boas-vindas do pygame é impresso em stdout — que aqui é o
# canal IPC. Silenciá-lo ANTES do import evita sujar os eventos.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

# Importação condicional do pygame (o modo interativo funciona sem ele)
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

logger = logging.getLogger("hardware_mock.gui")

# ---------------------------------------------------------------------------
#  Constantes do tabuleiro
# ---------------------------------------------------------------------------

FILES = "abcdefgh"
RANKS = "12345678"

# ---------------------------------------------------------------------------
#  Layout (pixels)
# ---------------------------------------------------------------------------

BOARD_SIZE = int(os.environ.get("CHESS_MOCK_BOARD_SIZE", "560"))

MARGIN = 30            # Margem laterais (coordenadas das fileiras)
HEADER_HEIGHT = 34     # Faixa de título no topo
COORD_HEIGHT = 22      # Faixa das coordenadas (colunas) abaixo do tabuleiro
TOOLBAR_HEIGHT = 48    # Barra de botões de ação
STATUS_HEIGHT = 58     # Barra de status inferior
BEVEL = 4              # Espessura do relevo dos botões
GUI_FPS = 30

# ---------------------------------------------------------------------------
#  Cores (RGB)
# ---------------------------------------------------------------------------

BG_COLOR = (28, 30, 34)
PANEL_COLOR = (38, 41, 46)
SEPARATOR_COLOR = (60, 64, 70)
TEXT_COLOR = (232, 232, 232)
DIM_TEXT_COLOR = (145, 148, 152)
COORD_COLOR = (130, 120, 110)
LIGHT_FACE_COLOR = (208, 195, 174)   # Botão de casa clara (solto)
DARK_FACE_COLOR = (150, 122, 96)     # Botão de casa escura (solto)
TOOL_FACE_COLOR = (62, 66, 73)       # Botões da barra de ações
LED_COLOR = (86, 220, 126)           # Indicador de sensor ativo


class GUIUnavailable(RuntimeError):
    """pygame ausente ou nenhum display disponível (ex: sessão headless)."""


class SensorGridLike(Protocol):
    """Interface mínima esperada do grid de sensores."""

    state: dict[str, bool]

    def get(self, square: str) -> bool: ...

    def set(self, square: str, value: bool) -> None: ...


# ---------------------------------------------------------------------------
#  Utilidades de desenho
# ---------------------------------------------------------------------------

def _scale(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    """Clareia (factor > 1) ou escurece (factor < 1) uma cor RGB."""
    return tuple(max(0, min(255, int(c * factor))) for c in color)


def _draw_bevel_button(
    surface: "pygame.Surface",
    rect: "pygame.Rect",
    face_color: tuple[int, int, int],
    pressed: bool,
    bevel: int = BEVEL,
) -> "pygame.Rect":
    """Desenha um botão com relevo (solto) ou afundado (pressionado).

    O relevo é feito com duas bordas em L: uma clara e uma escura. Trocar
    qual fica em cima inverte a sensação de profundidade.

    Returns:
        Rect da face interna do botão (útil para posicionar conteúdo).
    """
    x, y, w, h = rect
    light = _scale(face_color, 1.34)
    dark = _scale(face_color, 0.52)
    top_left, bottom_right = (dark, light) if pressed else (light, dark)

    # Borda superior-esquerda
    pygame.draw.polygon(surface, top_left, [
        (x, y), (x + w, y), (x + w - bevel, y + bevel),
        (x + bevel, y + bevel), (x + bevel, y + h - bevel), (x, y + h),
    ])
    # Borda inferior-direita
    pygame.draw.polygon(surface, bottom_right, [
        (x + w, y), (x + w, y + h), (x, y + h),
        (x + bevel, y + h - bevel), (x + w - bevel, y + h - bevel),
        (x + w - bevel, y + bevel),
    ])

    inner = pygame.Rect(x + bevel, y + bevel, w - 2 * bevel, h - 2 * bevel)
    pygame.draw.rect(surface, face_color, inner)
    return inner


def _sysfont(size: int, bold: bool = False) -> "pygame.font.Font":
    """Cria uma fonte do sistema, tentando várias famílias.

    Apenas texto ASCII é desenhado aqui — os indicadores de sensor são
    círculos desenhados, não glifos — então qualquer fonte serve.
    """
    return pygame.font.SysFont("dejavusans,freesans,arial", size, bold=bold)


# ---------------------------------------------------------------------------
#  GUI
# ---------------------------------------------------------------------------

class SensorBoardGUI:
    """Matriz 8×8 de botões que representa os reed switches do tabuleiro.

    Args:
        grid: Grid de sensores (precisa de `get`, `set` e `state`).
        on_change: Callback que publica as mudanças ({casa: 0|1}) via IPC.
        initial_state: Estado usado pelo botão "Reset" (padrão: cópia do
            estado do grid no momento da construção).
        board_size: Lado do tabuleiro em pixels.
        flip: Se True, desenha com a fileira 1 no topo (visão das pretas).
        info: Texto informativo exibido no cabeçalho.
    """

    def __init__(
        self,
        grid: SensorGridLike,
        on_change: Callable[[dict[str, int]], None],
        *,
        initial_state: Optional[dict[str, bool]] = None,
        board_size: int = BOARD_SIZE,
        flip: bool = False,
        info: str = "",
    ):
        self._grid = grid
        self._on_change = on_change
        self._initial_state = dict(initial_state or grid.state)
        self._flip = flip
        self._info = info

        # Geometria — o lado é arredondado para múltiplo de 8
        self._square = max(32, board_size // 8)
        self._board_size = self._square * 8
        self._board_top = HEADER_HEIGHT + 6
        self._width = self._board_size + 2 * MARGIN
        self._height = (
            self._board_top + self._board_size + COORD_HEIGHT
            + TOOLBAR_HEIGHT + STATUS_HEIGHT
        )

        # Estado de interação
        self._running = False
        self._dirty = True
        self._hover_square: Optional[str] = None
        self._hover_button: Optional[dict] = None
        self._active_button: Optional[dict] = None
        self._painting = False        # Botão do mouse mantido pressionado
        self._paint_value = False     # Estado aplicado durante o arraste
        self._painted: set[str] = set()
        self._last_event = ""

        # pygame
        self._screen: Optional["pygame.Surface"] = None
        self._clock: Optional["pygame.time.Clock"] = None
        self._buttons: list[dict] = []
        self._font_label: Optional["pygame.font.Font"] = None
        self._font_coord: Optional["pygame.font.Font"] = None
        self._font_ui: Optional["pygame.font.Font"] = None
        self._font_ui_bold: Optional["pygame.font.Font"] = None

    # -- ciclo de vida ------------------------------------------------------

    def run(self) -> None:
        """Abre a janela e roda o loop de eventos até o usuário sair.

        Raises:
            GUIUnavailable: se o pygame não estiver instalado ou não houver
                display disponível.
        """
        self._start()
        try:
            while self._running:
                self._handle_events()
                if self._dirty:
                    self._draw()
                    self._dirty = False
                self._clock.tick(GUI_FPS)
        finally:
            self.close()

    def _start(self) -> None:
        """Inicializa o pygame, a janela e as fontes."""
        if not PYGAME_AVAILABLE:
            raise GUIUnavailable(
                "pygame não está instalado (pip install pygame)"
            )

        try:
            pygame.init()
            self._screen = pygame.display.set_mode((self._width, self._height))
        except pygame.error as exc:
            pygame.quit()
            raise GUIUnavailable(f"não foi possível abrir a janela: {exc}") from exc

        pygame.display.set_caption("Hardware Mock — Matriz de Reed Switches")
        self._clock = pygame.time.Clock()

        try:
            self._font_label = _sysfont(max(10, self._square // 6))
            self._font_coord = _sysfont(13)
            self._font_ui = _sysfont(14)
            self._font_ui_bold = _sysfont(14, bold=True)
        except (NotImplementedError, pygame.error) as exc:
            # Build do pygame sem o módulo font (falta libz/freetype).
            pygame.quit()
            raise GUIUnavailable(f"módulo de fontes indisponível: {exc}") from exc

        self._build_toolbar()
        self._running = True
        self._dirty = True

        logger.info(
            "GUI do mock iniciada — janela %dx%d, casa %dpx",
            self._width, self._height, self._square,
        )

    def close(self) -> None:
        """Fecha a janela e libera o pygame."""
        self._running = False
        if PYGAME_AVAILABLE and pygame.get_init():
            pygame.quit()

    def __enter__(self):
        self._start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # -- geometria ---------------------------------------------------------

    def _build_toolbar(self) -> None:
        """Cria os botões de ação distribuídos na largura da janela."""
        specs = [
            ("Reset (R)", self._action_reset),
            ("Limpar (C)", self._action_clear),
            ("Inverter (F)", self._action_flip),
            ("Sair (Esc)", self._action_quit),
        ]
        gap = 8
        top = self._board_top + self._board_size + COORD_HEIGHT
        usable = self._width - 2 * MARGIN - gap * (len(specs) - 1)
        button_width = usable // len(specs)

        self._buttons = []
        for i, (label, action) in enumerate(specs):
            rect = pygame.Rect(
                MARGIN + i * (button_width + gap),
                top + 6,
                button_width,
                TOOLBAR_HEIGHT - 14,
            )
            self._buttons.append({"label": label, "action": action, "rect": rect})

    def _square_name(self, col: int, row: int) -> str:
        """Converte coluna/linha da tela (row 0 = topo) em nome de casa."""
        if self._flip:
            return f"{FILES[7 - col]}{RANKS[row]}"
        return f"{FILES[col]}{RANKS[7 - row]}"

    def _square_rect(self, col: int, row: int) -> "pygame.Rect":
        """Retângulo do botão de uma casa (com folga entre casas)."""
        return pygame.Rect(
            MARGIN + col * self._square + 2,
            self._board_top + row * self._square + 2,
            self._square - 4,
            self._square - 4,
        )

    def _square_at(self, pos: tuple[int, int]) -> Optional[str]:
        """Retorna a casa sob o cursor, ou None se estiver fora do tabuleiro."""
        bx = pos[0] - MARGIN
        by = pos[1] - self._board_top
        if not (0 <= bx < self._board_size and 0 <= by < self._board_size):
            return None
        return self._square_name(bx // self._square, by // self._square)

    def _button_at(self, pos: tuple[int, int]) -> Optional[dict]:
        """Retorna o botão da barra de ações sob o cursor, se houver."""
        for button in self._buttons:
            if button["rect"].collidepoint(pos):
                return button
        return None

    # -- eventos -----------------------------------------------------------

    def _handle_events(self) -> None:
        """Processa a fila de eventos do pygame."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._running = False

            elif event.type == pygame.KEYDOWN:
                self._handle_keydown(event.key)

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_mouse_down(event.pos)

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self._handle_mouse_up(event.pos)

            elif event.type == pygame.MOUSEMOTION:
                self._handle_mouse_motion(event.pos)

    def _handle_keydown(self, key: int) -> None:
        """Atalhos de teclado."""
        if key in (pygame.K_ESCAPE, pygame.K_q):
            self._action_quit()
        elif key == pygame.K_r:
            self._action_reset()
        elif key == pygame.K_c:
            self._action_clear()
        elif key == pygame.K_f:
            self._action_flip()

    def _handle_mouse_down(self, pos: tuple[int, int]) -> None:
        """Clique: aciona um botão da barra ou alterna um sensor."""
        button = self._button_at(pos)
        if button is not None:
            self._active_button = button
            self._dirty = True
            return

        square = self._square_at(pos)
        if square is None:
            return

        # O primeiro clique define o estado que o arraste vai "pintar"
        self._painting = True
        self._paint_value = not self._grid.get(square)
        self._painted = {square}
        self._set_square(square, self._paint_value)

    def _handle_mouse_up(self, pos: tuple[int, int]) -> None:
        """Soltar o mouse: executa a ação do botão pressionado."""
        self._painting = False
        self._painted.clear()

        button, self._active_button = self._active_button, None
        if button is not None:
            self._dirty = True
            if button["rect"].collidepoint(pos):
                button["action"]()

    def _handle_mouse_motion(self, pos: tuple[int, int]) -> None:
        """Atualiza o realce sob o cursor e pinta casas durante o arraste."""
        square = self._square_at(pos)
        button = self._button_at(pos)

        if square != self._hover_square or button is not self._hover_button:
            self._hover_square = square
            self._hover_button = button
            self._dirty = True

        if self._painting and square is not None and square not in self._painted:
            self._painted.add(square)
            self._set_square(square, self._paint_value)

    # -- ações -------------------------------------------------------------

    def _action_quit(self) -> None:
        """Encerra a GUI."""
        self._running = False

    def _action_reset(self) -> None:
        """Volta os sensores ao estado inicial."""
        self._apply_state(self._initial_state)

    def _action_clear(self) -> None:
        """Desliga todos os sensores (tabuleiro vazio)."""
        self._apply_state({sq: False for sq in self._grid.state})

    def _action_flip(self) -> None:
        """Inverte a orientação do tabuleiro na tela."""
        self._flip = not self._flip
        self._dirty = True

    # -- mudanças de estado ------------------------------------------------

    def _set_square(self, square: str, value: bool) -> None:
        """Altera um sensor e publica o evento, se houve mudança."""
        if self._grid.get(square) == value:
            return
        self._grid.set(square, value)
        self._emit({square: int(value)})
        self._dirty = True

    def _apply_state(self, target: dict[str, bool]) -> None:
        """Aplica um estado completo, publicando as diferenças num só evento."""
        changes: dict[str, int] = {}
        for square, value in target.items():
            if self._grid.get(square) != value:
                self._grid.set(square, value)
                changes[square] = int(value)
        if changes:
            self._emit(changes)
        self._dirty = True

    def _emit(self, changes: dict[str, int]) -> None:
        """Publica as mudanças via callback IPC."""
        try:
            self._on_change(changes)
        except (OSError, ValueError) as exc:
            # Canal fechado (o processo Python encerrou): não há mais
            # motivo para manter a janela aberta.
            logger.warning("Falha ao enviar evento IPC (%s) — encerrando.", exc)
            self._running = False
            return
        self._last_event = ",".join(f"{sq}:{st}" for sq, st in changes.items())

    # -- desenho -----------------------------------------------------------

    def _draw(self) -> None:
        """Redesenha a janela inteira."""
        self._screen.fill(BG_COLOR)
        self._draw_header()
        for row in range(8):
            for col in range(8):
                self._draw_square_button(col, row)
        self._draw_coordinates()
        self._draw_toolbar()
        self._draw_status_bar()
        pygame.display.flip()

    def _draw_header(self) -> None:
        """Título e informação de configuração no topo."""
        title = self._font_ui_bold.render("HARDWARE MOCK", True, TEXT_COLOR)
        self._screen.blit(title, (MARGIN, 10))

        if not self._info:
            return

        # A informação só é desenhada se couber sem invadir o título
        # (ela também vai para o log, então omitir aqui não perde nada).
        info = self._font_ui.render(self._info, True, DIM_TEXT_COLOR)
        if MARGIN + title.get_width() + 16 + info.get_width() <= self._width - MARGIN:
            self._screen.blit(
                info, info.get_rect(topright=(self._width - MARGIN, 11))
            )

    def _draw_square_button(self, col: int, row: int) -> None:
        """Desenha o botão de uma casa: afundado se o sensor está ativo."""
        square = self._square_name(col, row)
        pressed = self._grid.get(square)

        base = LIGHT_FACE_COLOR if (col + row) % 2 == 0 else DARK_FACE_COLOR
        face = _scale(base, 0.62) if pressed else base

        inner = _draw_bevel_button(
            self._screen, self._square_rect(col, row), face, pressed
        )

        # Realce do cursor
        if square == self._hover_square:
            overlay = pygame.Surface(inner.size, pygame.SRCALPHA)
            overlay.fill((255, 255, 255, 28))
            self._screen.blit(overlay, inner.topleft)

        # Nome da casa no canto — a cor segue a luminância da face para
        # continuar legível nas casas escuras pressionadas.
        luminance = 0.299 * face[0] + 0.587 * face[1] + 0.114 * face[2]
        label_color = (240, 236, 228) if luminance < 110 else _scale(face, 0.42)
        label = self._font_label.render(square, True, label_color)
        self._screen.blit(label, (inner.x + 5, inner.y + 3))

        # LED do sensor ativo
        if pressed:
            radius = max(5, self._square // 6)
            center = inner.center
            pygame.draw.circle(self._screen, _scale(LED_COLOR, 0.35), center, radius + 4)
            pygame.draw.circle(self._screen, LED_COLOR, center, radius)
            pygame.draw.circle(
                self._screen, _scale(LED_COLOR, 1.6),
                (center[0] - radius // 3, center[1] - radius // 3),
                max(2, radius // 4),
            )

    def _draw_coordinates(self) -> None:
        """Coordenadas: colunas abaixo do tabuleiro, fileiras à esquerda."""
        for i in range(8):
            file_label = FILES[7 - i] if self._flip else FILES[i]
            text = self._font_coord.render(file_label, True, COORD_COLOR)
            self._screen.blit(text, text.get_rect(center=(
                MARGIN + i * self._square + self._square // 2,
                self._board_top + self._board_size + COORD_HEIGHT // 2,
            )))

            rank_label = RANKS[i] if self._flip else RANKS[7 - i]
            text = self._font_coord.render(rank_label, True, COORD_COLOR)
            self._screen.blit(text, text.get_rect(center=(
                MARGIN // 2,
                self._board_top + i * self._square + self._square // 2,
            )))

    def _draw_toolbar(self) -> None:
        """Barra de botões de ação."""
        for button in self._buttons:
            pressed = button is self._active_button
            face = TOOL_FACE_COLOR
            if button is self._hover_button and not pressed:
                face = _scale(face, 1.18)

            inner = _draw_bevel_button(
                self._screen, button["rect"], face, pressed, bevel=3
            )
            text = self._font_ui.render(button["label"], True, TEXT_COLOR)
            self._screen.blit(text, text.get_rect(center=inner.center))

    def _draw_status_bar(self) -> None:
        """Barra inferior: último evento IPC e contagem de sensores ativos."""
        top = self._height - STATUS_HEIGHT
        pygame.draw.rect(
            self._screen, PANEL_COLOR,
            pygame.Rect(0, top, self._width, STATUS_HEIGHT),
        )
        pygame.draw.line(
            self._screen, SEPARATOR_COLOR, (0, top), (self._width, top), 1
        )

        # Último evento enviado por stdout
        prefix = self._font_ui.render("Último evento IPC:", True, DIM_TEXT_COLOR)
        self._screen.blit(prefix, (12, top + 10))

        if self._last_event:
            event_text = self._font_ui_bold.render(self._last_event, True, LED_COLOR)
        else:
            event_text = self._font_ui.render(
                "(nenhum — clique numa casa)", True, DIM_TEXT_COLOR
            )
        self._screen.blit(event_text, (12 + prefix.get_width() + 8, top + 10))

        # Contagem e ajuda
        active = sum(1 for v in self._grid.state.values() if v)
        hint = self._font_ui.render(
            f"{active} sensores ativos  ·  clique alterna a casa  ·  "
            f"arraste para pintar várias",
            True, DIM_TEXT_COLOR,
        )
        self._screen.blit(hint, (12, top + 32))
