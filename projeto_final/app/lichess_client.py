"""
lichess_client.py — Interface com a Lichess Board API.

Permite ao tabuleiro físico jogar partidas online contra oponentes
humanos via Lichess. Utiliza a Board API (não a Bot API), que é
destinada a contas de jogadores humanos com tabuleiros externos.

Funcionalidades:
  - Criar desafios (seek)
  - Enviar jogadas do jogador
  - Receber jogadas do oponente via stream HTTP (NDJSON)
  - Gerenciar o ciclo de vida da partida

Referência: https://lichess.org/api#tag/Board
"""

import json
import logging
import threading
from typing import Optional, Generator, Callable

import requests

from app.config import LICHESS_TOKEN, LICHESS_API_URL, LICHESS_TIME_MINUTES, LICHESS_INCREMENT

logger = logging.getLogger(__name__)


class LichessClient:
    """Cliente para a Lichess Board API.

    Gerencia uma partida online: cria challenges, envia jogadas e
    recebe eventos do jogo via stream HTTP.
    """

    def __init__(
        self,
        token: str = LICHESS_TOKEN,
        api_url: str = LICHESS_API_URL,
    ):
        """Inicializa o cliente Lichess.

        Args:
            token: Token OAuth2 do Lichess.
            api_url: URL base da API (padrão: https://lichess.org).
        """
        self._token = token
        self._api_url = api_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/x-ndjson",
        })
        self._game_id: Optional[str] = None
        self._player_color: Optional[str] = None
        self._stream_thread: Optional[threading.Thread] = None
        self._running = False
        self._event_callback: Optional[Callable] = None

    @property
    def game_id(self) -> Optional[str]:
        """ID da partida atual."""
        return self._game_id

    @property
    def player_color(self) -> Optional[str]:
        """Cor do jogador na partida atual ('white' ou 'black')."""
        return self._player_color

    def get_account(self) -> dict:
        """Obtém informações da conta do jogador.

        Returns:
            Dicionário com dados da conta.

        Raises:
            requests.HTTPError: Se a requisição falhar.
        """
        response = self._session.get(f"{self._api_url}/api/account")
        response.raise_for_status()
        data = response.json()
        logger.info("Conta Lichess: %s", data.get("username", "desconhecido"))
        return data

    def create_seek(
        self,
        time_minutes: int = LICHESS_TIME_MINUTES,
        increment: int = LICHESS_INCREMENT,
        rated: bool = False,
        color: str = "random",
    ) -> str:
        """Cria um seek (busca por oponente).

        Args:
            time_minutes: Tempo inicial em minutos.
            increment: Incremento por jogada em segundos.
            rated: Se a partida é ranqueada.
            color: Cor desejada ('white', 'black' ou 'random').

        Returns:
            ID da partida criada.
        """
        logger.info(
            "Criando seek: %d+%d, rated=%s, color=%s",
            time_minutes, increment, rated, color,
        )

        data = {
            "rated": str(rated).lower(),
            "time": str(time_minutes),
            "increment": str(increment),
            "color": color,
        }

        # O endpoint de seek usa text/plain e retorna via stream
        response = self._session.post(
            f"{self._api_url}/api/board/seek",
            data=data,
            stream=True,
        )
        response.raise_for_status()

        # Lê a resposta do stream para obter o game ID
        for line in response.iter_lines(decode_unicode=True):
            if line:
                try:
                    event = json.loads(line)
                    if event.get("type") == "gameStart":
                        self._game_id = event["game"]["gameId"]
                        self._player_color = event["game"].get("color", "white")
                        logger.info(
                            "Partida iniciada: %s (cor: %s)",
                            self._game_id, self._player_color,
                        )
                        return self._game_id
                except json.JSONDecodeError:
                    continue

        raise RuntimeError("Não foi possível criar a partida via seek.")

    def accept_challenge(self, challenge_id: str) -> None:
        """Aceita um desafio recebido.

        Args:
            challenge_id: ID do desafio.
        """
        response = self._session.post(
            f"{self._api_url}/api/challenge/{challenge_id}/accept"
        )
        response.raise_for_status()
        logger.info("Desafio aceito: %s", challenge_id)

    def send_move(self, move_uci: str, game_id: Optional[str] = None) -> bool:
        """Envia uma jogada para a partida atual.

        Args:
            move_uci: Jogada em notação UCI (ex: 'e2e4').
            game_id: ID da partida (usa a atual se None).

        Returns:
            True se a jogada foi aceita pelo servidor.
        """
        gid = game_id or self._game_id
        if not gid:
            logger.error("Nenhuma partida ativa para enviar jogada.")
            return False

        url = f"{self._api_url}/api/board/game/{gid}/move/{move_uci}"
        logger.info("Enviando jogada: %s (partida: %s)", move_uci, gid)

        try:
            response = self._session.post(url)
            if response.status_code == 200:
                logger.info("Jogada aceita pelo Lichess.")
                return True
            else:
                logger.warning(
                    "Jogada rejeitada — Status: %d, Resposta: %s",
                    response.status_code, response.text,
                )
                return False
        except requests.RequestException as exc:
            logger.error("Erro ao enviar jogada: %s", exc)
            return False

    def stream_game_events(
        self,
        game_id: Optional[str] = None,
    ) -> Generator[dict, None, None]:
        """Gera eventos do jogo via stream HTTP (NDJSON).

        Yields:
            Dicionários com eventos do jogo. Tipos principais:
            - gameFull: Estado completo do jogo (início do stream)
            - gameState: Atualização do estado (nova jogada, etc.)
            - chatLine: Mensagem no chat

        Args:
            game_id: ID da partida (usa a atual se None).
        """
        gid = game_id or self._game_id
        if not gid:
            logger.error("Nenhuma partida ativa para stream.")
            return

        url = f"{self._api_url}/api/board/game/stream/{gid}"
        logger.info("Abrindo stream de eventos: %s", gid)

        try:
            response = self._session.get(url, stream=True)
            response.raise_for_status()

            for line in response.iter_lines(decode_unicode=True):
                if not self._running:
                    break
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    logger.debug("Evento Lichess: %s", event.get("type", "?"))
                    yield event
                except json.JSONDecodeError:
                    continue

        except requests.RequestException as exc:
            logger.error("Erro no stream do jogo: %s", exc)

    def start_game_stream(
        self,
        callback: Callable[[dict], None],
        game_id: Optional[str] = None,
    ) -> None:
        """Inicia o stream de eventos do jogo em uma thread separada.

        Args:
            callback: Função chamada para cada evento recebido.
            game_id: ID da partida (usa a atual se None).
        """
        self._running = True
        self._event_callback = callback

        self._stream_thread = threading.Thread(
            target=self._stream_loop,
            args=(game_id,),
            name="LichessStream",
            daemon=True,
        )
        self._stream_thread.start()

    def _stream_loop(self, game_id: Optional[str]) -> None:
        """Loop de leitura do stream em thread separada."""
        try:
            for event in self.stream_game_events(game_id):
                if self._event_callback:
                    self._event_callback(event)
                if not self._running:
                    break
        except Exception as exc:
            logger.error("Erro no stream loop: %s", exc)

    def stream_incoming_events(self) -> Generator[dict, None, None]:
        """Stream de eventos da conta (desafios, partidas iniciadas, etc.).

        Yields:
            Dicionários com eventos. Tipos:
            - challenge: Desafio recebido
            - challengeCanceled: Desafio cancelado
            - challengeDeclined: Desafio recusado
            - gameStart: Partida iniciada
            - gameFinish: Partida finalizada
        """
        url = f"{self._api_url}/api/stream/event"
        logger.info("Abrindo stream de eventos da conta...")

        try:
            response = self._session.get(url, stream=True)
            response.raise_for_status()

            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    yield event
                except json.JSONDecodeError:
                    continue

        except requests.RequestException as exc:
            logger.error("Erro no stream de eventos: %s", exc)

    def resign(self, game_id: Optional[str] = None) -> bool:
        """Desiste da partida.

        Args:
            game_id: ID da partida (usa a atual se None).

        Returns:
            True se a resignação foi aceita.
        """
        gid = game_id or self._game_id
        if not gid:
            return False

        try:
            response = self._session.post(
                f"{self._api_url}/api/board/game/{gid}/resign"
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def close(self) -> None:
        """Encerra o cliente e fecha conexões."""
        self._running = False

        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=3)

        self._session.close()
        logger.info("Cliente Lichess encerrado.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
