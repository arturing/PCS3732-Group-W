"""
stockfish_engine.py — Interface UCI com a engine Stockfish.

Utiliza a classe chess.engine.SimpleEngine da biblioteca python-chess
para se comunicar com o Stockfish via protocolo UCI (Universal Chess
Interface).

Responsabilidades:
  - Iniciar e manter a conexão com o processo Stockfish
  - Enviar posições (FEN + movimentos) para a engine
  - Receber a melhor jogada calculada
  - Configurar parâmetros (nível de habilidade, limites de tempo)
"""

import logging
from typing import Optional

import chess
import chess.engine

from app.config import STOCKFISH_PATH, STOCKFISH_TIME_LIMIT, STOCKFISH_DEPTH, STOCKFISH_SKILL_LEVEL

logger = logging.getLogger(__name__)


class StockfishEngine:
    """Interface com a engine Stockfish via protocolo UCI.

    Encapsula chess.engine.SimpleEngine e fornece métodos simplificados
    para obter jogadas da engine.
    """

    def __init__(
        self,
        path: str = STOCKFISH_PATH,
        time_limit: float = STOCKFISH_TIME_LIMIT,
        depth: Optional[int] = STOCKFISH_DEPTH,
        skill_level: Optional[int] = STOCKFISH_SKILL_LEVEL,
    ):
        """Inicializa a interface com o Stockfish.

        Args:
            path: Caminho para o binário do Stockfish.
            time_limit: Tempo máximo de cálculo por jogada (segundos).
            depth: Profundidade máxima de busca (None = usar tempo).
            skill_level: Nível de habilidade 0-20 (None = não configurar).
        """
        self._path = path
        self._time_limit = time_limit
        self._depth = depth
        self._skill_level = skill_level
        self._engine: Optional[chess.engine.SimpleEngine] = None

    def start(self) -> None:
        """Inicia a engine Stockfish."""
        try:
            logger.info("Iniciando Stockfish em: %s", self._path)
            self._engine = chess.engine.SimpleEngine.popen_uci(self._path)

            # Configura nível de habilidade se especificado
            if self._skill_level is not None:
                self._engine.configure({"Skill Level": self._skill_level})
                logger.info("Nível de habilidade: %d", self._skill_level)

            logger.info("Stockfish iniciado com sucesso.")

        except FileNotFoundError:
            logger.error(
                "Stockfish não encontrado em '%s'. "
                "Instale o Stockfish e configure o caminho via "
                "variável de ambiente CHESS_STOCKFISH_PATH.",
                self._path,
            )
            raise
        except Exception as exc:
            logger.error("Erro ao iniciar Stockfish: %s", exc)
            raise

    def get_best_move(self, board: chess.Board) -> chess.Move:
        """Obtém a melhor jogada para a posição atual.

        Args:
            board: Estado atual do tabuleiro.

        Returns:
            A melhor jogada calculada pela engine.

        Raises:
            RuntimeError: Se a engine não estiver iniciada.
            chess.engine.EngineTerminatedError: Se a engine encerrou.
        """
        if self._engine is None:
            raise RuntimeError("Stockfish não está iniciado. Chame start() primeiro.")

        # Define o limite de cálculo
        if self._depth is not None:
            limit = chess.engine.Limit(depth=self._depth)
        else:
            limit = chess.engine.Limit(time=self._time_limit)

        logger.debug(
            "Calculando jogada — FEN: %s, Limite: %s",
            board.fen(), limit,
        )

        result = self._engine.play(board, limit)

        if result.move is None:
            raise RuntimeError("Stockfish não retornou nenhuma jogada.")

        logger.info("Stockfish jogou: %s", result.move.uci())
        return result.move

    def analyze(
        self,
        board: chess.Board,
        time_limit: Optional[float] = None,
    ) -> chess.engine.InfoDict:
        """Analisa a posição atual e retorna informações da engine.

        Args:
            board: Estado atual do tabuleiro.
            time_limit: Tempo de análise (usa o padrão se None).

        Returns:
            Dicionário com informações da análise (score, pv, etc.).
        """
        if self._engine is None:
            raise RuntimeError("Stockfish não está iniciado.")

        t = time_limit if time_limit is not None else self._time_limit
        limit = chess.engine.Limit(time=t)

        info = self._engine.analyse(board, limit)
        return info

    @property
    def is_running(self) -> bool:
        """Verifica se a engine está rodando."""
        return self._engine is not None

    def stop(self) -> None:
        """Encerra a engine Stockfish."""
        if self._engine:
            try:
                self._engine.quit()
                logger.info("Stockfish encerrado.")
            except Exception as exc:
                logger.warning("Erro ao encerrar Stockfish: %s", exc)
            finally:
                self._engine = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
