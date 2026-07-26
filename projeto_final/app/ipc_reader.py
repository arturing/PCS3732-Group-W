"""
ipc_reader.py — Módulo IPC (Named Pipe / stdin / subprocess).

Responsável por receber dados do processo C (ou mock),
desserializar os eventos de mudança do tabuleiro e entregá-los
ao motor de estado do jogo.

Protocolo de eventos:
    Cada linha contém pares "casa:estado" separados por vírgula.
    Exemplo: "e2:0,e4:1\n"
    - casa: notação algébrica (a1–h8)
    - estado: 0 (desocupada) ou 1 (ocupada)

Modos suportados:
    - 'subprocess': Inicia o processo C/mock como subprocesso e lê stdout
    - 'stdin': Lê da entrada padrão (útil para piping)
    - 'pipe': Lê de um Named Pipe / FIFO (somente Linux)
"""

import os
import sys
import logging
import subprocess
import threading
from queue import Queue, Empty
from typing import Optional

from app.config import (
    IPC_MODE, PIPE_PATH, C_PROCESS_PATH,
    EVENT_SEPARATOR, FIELD_SEPARATOR, FILES, RANKS,
)

logger = logging.getLogger(__name__)


def parse_event(line: str) -> Optional[dict[str, int]]:
    """Desserializa uma linha de evento IPC.

    Args:
        line: Linha de texto no formato "a1:0,e4:1"

    Returns:
        Dicionário {casa: estado} ou None se a linha for inválida.
        Exemplo: {"e2": 0, "e4": 1}
    """
    line = line.strip()
    if not line:
        return None

    changes: dict[str, int] = {}
    try:
        pairs = line.split(EVENT_SEPARATOR)
        for pair in pairs:
            pair = pair.strip()
            if not pair:
                continue
            square, state_str = pair.split(FIELD_SEPARATOR)
            square = square.strip().lower()

            # Validação do nome da casa
            if len(square) != 2 or square[0] not in FILES or square[1] not in RANKS:
                logger.warning("Casa inválida no evento IPC: '%s'", square)
                return None

            state = int(state_str.strip())
            if state not in (0, 1):
                logger.warning("Estado inválido no evento IPC: '%s'", state_str)
                return None

            changes[square] = state

    except (ValueError, IndexError) as exc:
        logger.warning("Erro ao parsear evento IPC '%s': %s", line, exc)
        return None

    return changes if changes else None


class IPCReader:
    """Leitor de eventos IPC do processo C / mock.

    Lê eventos de uma fonte (subprocess, stdin ou named pipe)
    em uma thread separada e os coloca em uma fila thread-safe.
    """

    def __init__(
        self,
        mode: str = IPC_MODE,
        pipe_path: str = PIPE_PATH,
        process_path: str = C_PROCESS_PATH,
    ):
        self._mode = mode
        self._pipe_path = pipe_path
        self._process_path = process_path
        self._queue: Queue[dict[str, int]] = Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._process: Optional[subprocess.Popen] = None
        self._source = None  # file-like object para leitura

    def start(self) -> None:
        """Inicia a leitura de eventos em background."""
        if self._running:
            return

        self._running = True

        if self._mode == "subprocess":
            self._start_subprocess()
        elif self._mode == "stdin":
            self._source = sys.stdin
        elif self._mode == "pipe":
            self._start_pipe()
        else:
            raise ValueError(f"Modo IPC desconhecido: {self._mode}")

        self._thread = threading.Thread(
            target=self._read_loop,
            name="IPCReader",
            daemon=True,
        )
        self._thread.start()
        logger.info("IPCReader iniciado no modo '%s'", self._mode)

    def _start_subprocess(self) -> None:
        """Inicia o processo C/mock como subprocesso.

        No Windows, abre uma janela de console separada para que o
        usuário possa digitar jogadas interativamente. No Linux, o
        stdin/stderr são herdados do processo pai (terminal).
        """
        cmd = [sys.executable, self._process_path]
        logger.info("Iniciando subprocesso: %s", " ".join(cmd))

        popen_kwargs = dict(
            stdout=subprocess.PIPE,  # IPC events vêm por aqui
            text=True,
            bufsize=1,  # line-buffered
        )

        if sys.platform == "win32":
            # Abre console próprio: o mock mostra prompts no console
            # e o usuário digita lá. stdout continua piped para IPC.
            popen_kwargs["stdin"] = None       # console próprio
            popen_kwargs["stderr"] = None      # console próprio
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
        else:
            # No Linux, herda stdin/stderr do terminal pai
            popen_kwargs["stdin"] = None
            popen_kwargs["stderr"] = None

        self._process = subprocess.Popen(cmd, **popen_kwargs)
        self._source = self._process.stdout

    def _start_pipe(self) -> None:
        """Abre o Named Pipe (FIFO) para leitura. Somente Linux."""
        if sys.platform == "win32":
            raise OSError(
                "Named Pipes FIFO não são suportados no Windows. "
                "Use o modo 'subprocess' ou 'stdin'."
            )

        # Cria o FIFO se não existir
        if not os.path.exists(self._pipe_path):
            os.mkfifo(self._pipe_path)
            logger.info("FIFO criado em: %s", self._pipe_path)

        logger.info("Aguardando conexão no Named Pipe: %s", self._pipe_path)
        # open() bloqueia até que o outro lado abra para escrita
        self._source = open(self._pipe_path, "r")

    def _read_loop(self) -> None:
        """Loop de leitura em thread separada."""
        try:
            while self._running and self._source:
                line = self._source.readline()
                if not line:
                    # EOF — o processo C encerrou ou pipe foi fechado
                    logger.info("Fonte IPC encerrou (EOF).")
                    break

                event = parse_event(line)
                if event is not None:
                    self._queue.put(event)
                    logger.debug("Evento recebido: %s", event)

        except Exception as exc:
            if self._running:
                logger.error("Erro na leitura IPC: %s", exc)
        finally:
            self._running = False

    def read_event(self, timeout: float = 0.05) -> Optional[dict[str, int]]:
        """Lê o próximo evento da fila.

        Args:
            timeout: Tempo máximo de espera em segundos (padrão 50ms).

        Returns:
            Dicionário {casa: estado} ou None se não houver evento.
        """
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None

    def has_events(self) -> bool:
        """Verifica se há eventos pendentes na fila."""
        return not self._queue.empty()

    @property
    def is_running(self) -> bool:
        """Indica se o leitor está ativo."""
        return self._running

    def send_to_process(self, message: str) -> None:
        """Envia uma mensagem para o subprocesso (via stdin).

        Útil para enviar comandos ao mock (ex: forçar estado do tabuleiro).
        """
        if self._process and self._process.stdin:
            try:
                self._process.stdin.write(message + "\n")
                self._process.stdin.flush()
            except (OSError, BrokenPipeError) as exc:
                logger.error("Erro ao enviar para subprocesso: %s", exc)

    def stop(self) -> None:
        """Para a leitura e libera recursos."""
        self._running = False

        # Encerra o subprocesso se existir
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                self._process.kill()
            self._process = None

        # Fecha o source (exceto stdin)
        if self._source and self._source is not sys.stdin:
            try:
                self._source.close()
            except Exception:
                pass
            self._source = None

        # Aguarda a thread finalizar
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

        logger.info("IPCReader encerrado.")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
