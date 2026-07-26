"""
config.py — Configurações globais do Tabuleiro de Xadrez Eletrônico.

Centraliza constantes, caminhos e parâmetros configuráveis
utilizados por todos os módulos da camada Python.
"""

import os
import sys
from enum import Enum, auto
from pathlib import Path


# ---------------------------------------------------------------------------
#  Modo de jogo
# ---------------------------------------------------------------------------

class GameMode(Enum):
    """Modos de jogo suportados."""
    STOCKFISH = auto()   # Jogar contra a engine Stockfish
    LICHESS = auto()     # Jogar online via Lichess Board API


# ---------------------------------------------------------------------------
#  Cor do jogador físico
# ---------------------------------------------------------------------------

class PlayerColor(Enum):
    """Cor das peças do jogador no tabuleiro físico."""
    WHITE = "white"
    BLACK = "black"


# ---------------------------------------------------------------------------
#  IPC — Comunicação inter-processo
# ---------------------------------------------------------------------------

# Modo de IPC: 'pipe' (Named Pipe / FIFO), 'stdin' ou 'subprocess'
IPC_MODE = os.environ.get("CHESS_IPC_MODE", "subprocess")

# Caminho do Named Pipe (usado apenas no modo 'pipe', Linux)
PIPE_PATH = os.environ.get("CHESS_PIPE_PATH", "/tmp/chess_board_pipe")

# Caminho do executável do processo C (ou do mock)
C_PROCESS_PATH = os.environ.get(
    "CHESS_C_PROCESS",
    str(Path(__file__).resolve().parent.parent / "mock" / "hardware_mock.py")
)

# ---------------------------------------------------------------------------
#  Stockfish
# ---------------------------------------------------------------------------

# Caminho do binário do Stockfish
if sys.platform == "win32":
    _default_sf = "stockfish.exe"
else:
    _default_sf = "stockfish"

STOCKFISH_PATH = os.environ.get("CHESS_STOCKFISH_PATH", _default_sf)

# Tempo de cálculo da engine em segundos
STOCKFISH_TIME_LIMIT = float(os.environ.get("CHESS_STOCKFISH_TIME", "1.0"))

# Profundidade máxima de busca (None = sem limite, usa tempo)
STOCKFISH_DEPTH = os.environ.get("CHESS_STOCKFISH_DEPTH", None)
if STOCKFISH_DEPTH is not None:
    STOCKFISH_DEPTH = int(STOCKFISH_DEPTH)

# Nível de habilidade do Stockfish (0-20, None = não configurar)
STOCKFISH_SKILL_LEVEL = os.environ.get("CHESS_STOCKFISH_SKILL", None)
if STOCKFISH_SKILL_LEVEL is not None:
    STOCKFISH_SKILL_LEVEL = int(STOCKFISH_SKILL_LEVEL)

# ---------------------------------------------------------------------------
#  Lichess
# ---------------------------------------------------------------------------

# Token de API do Lichess (Board API requer token OAuth2)
LICHESS_TOKEN = os.environ.get("CHESS_LICHESS_TOKEN", "")

# URL base da API do Lichess
LICHESS_API_URL = os.environ.get("CHESS_LICHESS_API_URL", "https://lichess.org")

# Controle de tempo padrão para seek (minutos + incremento em segundos)
LICHESS_TIME_MINUTES = int(os.environ.get("CHESS_LICHESS_TIME", "10"))
LICHESS_INCREMENT = int(os.environ.get("CHESS_LICHESS_INCREMENT", "0"))

# ---------------------------------------------------------------------------
#  GUI
# ---------------------------------------------------------------------------

# Tamanho do tabuleiro em pixels (largura e altura do grid 8x8)
BOARD_SIZE = int(os.environ.get("CHESS_BOARD_SIZE", "640"))

# Altura da barra de status inferior
STATUS_BAR_HEIGHT = 60

# FPS do loop de renderização
GUI_FPS = 30

# Cores do tabuleiro (RGB)
LIGHT_SQUARE_COLOR = (240, 217, 181)     # Bege claro (madeira clara)
DARK_SQUARE_COLOR = (181, 136, 99)       # Marrom (madeira escura)
HIGHLIGHT_COLOR = (247, 247, 105, 128)   # Amarelo semi-transparente (último mov.)
INVALID_MOVE_COLOR = (220, 50, 50)       # Vermelho (movimento inválido)
BG_COLOR = (49, 46, 43)                  # Fundo escuro
STATUS_BG_COLOR = (39, 37, 34)           # Fundo da barra de status
TEXT_COLOR = (255, 255, 255)             # Texto branco
COORD_COLOR = (130, 120, 110)           # Coordenadas do tabuleiro

# ---------------------------------------------------------------------------
#  Protocolo de eventos IPC
# ---------------------------------------------------------------------------
# Formato: "a1:0,e4:1\n"
# Cada par "casa:estado" separado por vírgula
# Estado: 0 = desocupada, 1 = ocupada
# Linha terminada por newline

EVENT_SEPARATOR = ","
FIELD_SEPARATOR = ":"

# ---------------------------------------------------------------------------
#  Tabuleiro
# ---------------------------------------------------------------------------

# Colunas e linhas do tabuleiro para conversão de coordenadas
FILES = "abcdefgh"
RANKS = "12345678"

# Posição inicial FEN padrão
INITIAL_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
