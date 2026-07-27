"""
lichess_client.py — Interface com a Lichess Board API.

Permite ao tabuleiro físico jogar partidas online contra oponentes humanos
(ou contra a engine do próprio Lichess) via Board API, que é destinada a
contas de jogadores humanos usando tabuleiros externos.

Ciclo de vida de uma partida:

  1. `get_account()`          — valida o token e identifica a conta
  2. `start_account_stream()` — abre /api/stream/event em background. Ao
     conectar, o Lichess reenvia as partidas já em andamento como eventos
     `gameStart`, então este passo também serve para reencontrar um jogo.
  3. `create_seek()` (procura um humano) ou `challenge_ai()` (joga contra a
     engine hospedada no Lichess)
  4. `wait_for_game_start()`  — espera o `gameStart` correspondente
  5. `start_game_stream()`    — abre /api/board/game/stream/{id} em
     background; cada evento do jogo vai para o callback
  6. `send_move()`            — envia as jogadas feitas no tabuleiro físico

NOTA sobre o seek: `POST /api/board/seek` é *long-polling*. A resposta não
traz a partida — são só linhas em branco de keep-alive — e fechar a conexão
CANCELA a busca. Por isso o seek fica numa thread apenas segurando a conexão
aberta; quem anuncia a partida é o stream da conta.

Escopos de token necessários:
  - `board:play`      — obrigatório (jogar pela Board API)
  - `challenge:write` — apenas para `challenge_ai()`

Referência: https://lichess.org/api#tag/Board
"""

import json
import logging
import socket
import threading
from queue import Queue, Empty
from typing import Optional, Generator, Callable

import requests

from app.config import (
    LICHESS_TOKEN, LICHESS_API_URL, LICHESS_TIME_MINUTES, LICHESS_INCREMENT,
)

logger = logging.getLogger(__name__)

# Timeout das requisições comuns. Os streams usam só o timeout de conexão:
# ficam abertos por horas, com keep-alive do servidor a cada ~6 s.
REQUEST_TIMEOUT = 15.0
CONNECT_TIMEOUT = 10.0

NDJSON_HEADERS = {"Accept": "application/x-ndjson"}

# A Board API só aceita partidas em tempo real de *rapid* para cima. O Lichess
# estima a duração de uma partida em `limite + 40 x incremento` (40 lances) e
# recusa qualquer coisa abaixo de 8 minutos com {"global":["Invalid time
# control"]} — blitz e bullet não dão tempo de mexer as peças à mão.
# Verificado contra a API: 8+0 e 5+5 passam (480s e 500s), 7+0 e 5+4 não
# (420s e 460s).
BOARD_MIN_ESTIMATED_SECONDS = 480
ESTIMATED_MOVES = 40


class LichessError(RuntimeError):
    """Falha ao conversar com o Lichess (token inválido, escopo faltando...)."""


def estimate_game_seconds(time_minutes: float, increment: int) -> int:
    """Duração estimada de uma partida, pela conta que o Lichess faz."""
    return int(time_minutes * 60 + ESTIMATED_MOVES * increment)


def is_board_time_control(time_minutes: float, increment: int) -> bool:
    """Se o controle de tempo é aceito pela Board API (rapid ou mais lento)."""
    return (
        estimate_game_seconds(time_minutes, increment)
        >= BOARD_MIN_ESTIMATED_SECONDS
    )


def explain_time_control(time_minutes: float, increment: int) -> str:
    """Explica por que um controle de tempo é rápido demais e o que usar.

    As sugestões são as duas saídas mínimas: manter o tempo e aumentar o
    incremento, ou manter o incremento e aumentar o tempo.
    """
    estimated = estimate_game_seconds(time_minutes, increment)
    faltam = BOARD_MIN_ESTIMATED_SECONDS - estimated

    # Arredondamento para cima, para cair *em cima* ou acima do limite
    min_increment = increment + -(-faltam // ESTIMATED_MOVES)
    min_minutes = time_minutes + -(-faltam // 60)

    return (
        f"O controle de tempo {time_minutes:g}+{increment} é rápido demais "
        f"para a Board API do Lichess: ela só aceita rapid ou mais lento, ou "
        f"seja limite + 40 x incremento >= {BOARD_MIN_ESTIMATED_SECONDS}s "
        f"(esse dá {estimated}s). Use {time_minutes:g}+{min_increment} ou "
        f"{min_minutes:g}+{increment}, algo mais lento como 10+0, ou jogue "
        f"contra a engine local com --mode stockfish."
    )


class LichessClient:
    """Cliente para a Lichess Board API.

    Os streams (eventos da conta, eventos do jogo e o seek) rodam em threads
    daemon separadas. `close()` fecha as respostas HTTP, o que desbloqueia as
    threads presas na leitura.
    """

    def __init__(
        self,
        token: str = LICHESS_TOKEN,
        api_url: str = LICHESS_API_URL,
        token_origin: str = "",
    ):
        """Inicializa o cliente Lichess.

        Args:
            token: Token OAuth2 do Lichess (escopo `board:play`).
            api_url: URL base da API (padrão: https://lichess.org).
            token_origin: De onde o token veio, citado nas mensagens de erro
                de autenticação — são elas que precisam dizer *qual* token
                foi recusado.
        """
        self._token_origin = token_origin

        if not token:
            raise LichessError(
                "Token do Lichess não encontrado. Informe-o por --token-file "
                "ARQUIVO, pela variável CHESS_LICHESS_TOKEN, ou grave-o em "
                "'.lichess_token' na raiz do projeto (veja o README)."
            )

        self._token = token
        self._api_url = api_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {self._token}"})

        self._game_id: Optional[str] = None
        self._player_color: Optional[str] = None
        self._account: dict = {}

        # `_running` significa "cliente não encerrado": os geradores de stream
        # o consultam a cada linha para poderem parar em close().
        self._running = True
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []
        self._streams: list[requests.Response] = []

        # Eventos da conta (gameStart, challenge, ...) para wait_for_game_start
        self._account_events: "Queue[dict]" = Queue()

        # Motivo de o seek ter falhado, para quem está esperando desistir cedo
        self._seek_error: Optional[str] = None

        # Desafio enviado e ainda não aceito, cancelado no encerramento para
        # não deixar convite pendurado na conta.
        self._pending_challenge_id: Optional[str] = None

    # -- propriedades -------------------------------------------------------

    @property
    def game_id(self) -> Optional[str]:
        """ID da partida atual."""
        return self._game_id

    @property
    def player_color(self) -> Optional[str]:
        """Cor do jogador na partida atual ('white' ou 'black')."""
        return self._player_color

    @property
    def seek_error(self) -> Optional[str]:
        """Mensagem de erro se o seek foi recusado, senão None."""
        return self._seek_error

    @property
    def account_id(self) -> Optional[str]:
        """ID (username em minúsculas) da conta autenticada."""
        return self._account.get("id")

    @property
    def username(self) -> str:
        """Nome de usuário da conta autenticada."""
        return self._account.get("username", "?")

    # -- infraestrutura de stream ------------------------------------------

    def _spawn(self, name: str, target: Callable, *args) -> threading.Thread:
        """Roda `target` numa thread daemon registrada para o shutdown."""
        thread = threading.Thread(target=target, args=args, name=name, daemon=True)
        with self._lock:
            self._threads.append(thread)
        thread.start()
        return thread

    def _open_stream(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> Optional[requests.Response]:
        """Abre uma resposta em streaming e a registra para o shutdown."""
        try:
            response = self._session.request(
                method, url,
                stream=True,
                headers=NDJSON_HEADERS,
                timeout=(CONNECT_TIMEOUT, None),
                **kwargs,
            )
        except requests.RequestException as exc:
            logger.error("Falha ao abrir stream %s: %s", url, exc)
            return None

        if not response.ok:
            # O corpo da resposta é onde o Lichess diz *qual* campo recusou;
            # sem ele um 400 vira adivinhação.
            detail = response.text[:300].strip() or "(sem detalhe)"
            logger.error(
                "Falha ao abrir stream %s: HTTP %d — %s",
                url, response.status_code, detail,
            )
            response.close()
            return None

        with self._lock:
            self._streams.append(response)
        return response

    def _iter_ndjson(
        self,
        response: requests.Response,
    ) -> Generator[dict, None, None]:
        """Itera as linhas NDJSON de um stream, ignorando os keep-alive."""
        try:
            for line in response.iter_lines(decode_unicode=True):
                if not self._running:
                    break
                if not line:
                    continue  # linha em branco = keep-alive
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Linha não-JSON no stream: %r", line[:120])
        except Exception as exc:  # noqa: BLE001
            # Derrubar o socket para acordar esta thread (ver `_force_close`)
            # faz a leitura estourar de várias formas — inclusive AttributeError
            # vindo das entranhas do urllib3. Durante o shutdown isso é normal.
            if self._running:
                logger.error("Stream interrompido: %s", exc)
            else:
                logger.debug("Stream encerrado no shutdown: %s", exc)
        finally:
            with self._lock:
                if response in self._streams:
                    self._streams.remove(response)
            self._force_close(response)

    @staticmethod
    def _force_close(response: requests.Response) -> None:
        """Fecha o stream derrubando o socket por baixo dele.

        `Response.close()` sozinho não acorda uma thread parada em `recv()`:
        ela continua bloqueada até o servidor mandar alguma coisa — e um
        stream do Lichess pode ficar minutos em silêncio. `shutdown()` entrega
        um EOF imediato e desbloqueia a leitura, que é o que permite encerrar
        a aplicação sem esperar o servidor.
        """
        try:
            connection = getattr(response.raw, "_connection", None)
            sock = getattr(connection, "sock", None)
            if sock is not None:
                sock.shutdown(socket.SHUT_RDWR)
        except (OSError, AttributeError):
            pass  # já fechado, ou urllib3 mudou por dentro: seguir adiante

        try:
            response.close()
        except Exception:  # noqa: BLE001 — melhor esforço no shutdown
            pass

    # -- conta --------------------------------------------------------------

    def get_account(self) -> dict:
        """Obtém informações da conta autenticada.

        Returns:
            Dicionário com os dados da conta.

        Raises:
            LichessError: Se o token for inválido ou a API não responder.
        """
        try:
            response = self._session.get(
                f"{self._api_url}/api/account", timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as exc:
            raise LichessError(f"Não foi possível contatar o Lichess: {exc}") from exc

        if response.status_code == 401:
            source = f" (lido de {self._token_origin})" if self._token_origin else ""
            raise LichessError(
                f"Token do Lichess rejeitado (401){source}. Ele foi revogado, "
                f"está incompleto, ou não tem o escopo 'board:play'. Gere um "
                f"novo em https://lichess.org/account/oauth/token — e confira "
                f"se não há um --token antigo na linha de comando "
                f"sobrepondo o arquivo de token."
            )
        if not response.ok:
            raise LichessError(
                f"Erro ao consultar a conta: HTTP {response.status_code} — "
                f"{response.text[:200]}"
            )

        self._account = response.json()
        logger.info("Conta Lichess: %s", self.username)
        return self._account

    def start_account_stream(self) -> None:
        """Abre o stream de eventos da conta numa thread de background.

        Ao conectar, o Lichess reenvia os desafios pendentes e as partidas em
        andamento, então este stream é também a forma de reencontrar um jogo
        já começado (na web, por exemplo).
        """
        self._spawn("LichessAccountStream", self._run_account_stream)

    def _run_account_stream(self) -> None:
        """Alimenta a fila de eventos da conta até o cliente ser encerrado."""
        for event in self.stream_incoming_events():
            logger.debug("Evento da conta: %s", event.get("type", "?"))
            self._account_events.put(event)
        logger.info("Stream de eventos da conta encerrado.")

    def stream_incoming_events(self) -> Generator[dict, None, None]:
        """Stream de eventos da conta (desafios, partidas iniciadas, etc.).

        Yields:
            Dicionários com eventos. Tipos:
            - challenge: Desafio recebido
            - challengeCanceled / challengeDeclined
            - gameStart: Partida iniciada (ou já em andamento, na conexão)
            - gameFinish: Partida finalizada
        """
        logger.info("Abrindo stream de eventos da conta...")
        response = self._open_stream("GET", f"{self._api_url}/api/stream/event")
        if response is None:
            return
        yield from self._iter_ndjson(response)

    def wait_for_game_start(self, timeout: float = 1.0) -> Optional[dict]:
        """Espera o próximo evento `gameStart` do stream da conta.

        Descarta os outros tipos de evento. Deve ser chamada em laço pelo
        loop principal, para que a GUI continue respondendo durante a espera.

        Args:
            timeout: Tempo máximo de espera, em segundos.

        Returns:
            Dicionário com pelo menos `gameId` e (quando disponível) `color`,
            ou None se nada chegou dentro do timeout.
        """
        try:
            event = self._account_events.get(timeout=timeout)
        except Empty:
            return None

        if event.get("type") == "challenge":
            self._maybe_accept_challenge(event)
            return None

        if event.get("type") != "gameStart":
            return None

        game = event.get("game") or {}
        game_id = game.get("gameId") or game.get("id")
        if not game_id:
            logger.warning("gameStart sem ID de partida: %s", game)
            return None

        self._game_id = game_id
        self._pending_challenge_id = None   # aceito: não há o que cancelar
        self._player_color = game.get("color")
        logger.info(
            "Partida encontrada: %s (cor: %s)", game_id, self._player_color or "?"
        )
        return {"gameId": game_id, **game}

    # -- criação de partida -------------------------------------------------

    def create_seek(
        self,
        time_minutes: int = LICHESS_TIME_MINUTES,
        increment: int = LICHESS_INCREMENT,
        rated: bool = False,
    ) -> None:
        """Publica um seek (busca por oponente humano) em background.

        O seek é long-polling: a conexão precisa ficar aberta enquanto a busca
        estiver ativa (fechá-la cancela o seek), e a partida é anunciada pelo
        stream da conta — use `wait_for_game_start()` para recebê-la.

        NOTA: o seek não aceita escolha de cor — quem sorteia é o sistema de
        pareamento, e mandar um campo `color` faz o endpoint responder 400.
        Para escolher a cor é preciso desafiar alguém diretamente
        (/api/challenge/{user}) ou a IA (`challenge_ai`).

        Args:
            time_minutes: Tempo inicial em minutos.
            increment: Incremento por jogada em segundos.
            rated: Se a partida é ranqueada.

        Raises:
            LichessError: Se o controle de tempo for rápido demais para a
                Board API. É melhor recusar aqui, com a conta explicada, do
                que traduzir depois um 400 genérico do servidor.
        """
        if not is_board_time_control(time_minutes, increment):
            raise LichessError(explain_time_control(time_minutes, increment))

        logger.info(
            "Publicando seek: %d+%d, rated=%s (a cor é sorteada pelo Lichess)",
            time_minutes, increment, rated,
        )
        self._spawn("LichessSeek", self._run_seek, time_minutes, increment, rated)

    def _run_seek(
        self,
        time_minutes: int,
        increment: int,
        rated: bool,
    ) -> None:
        """Segura a conexão do seek aberta até o Lichess encerrá-la."""
        data = {
            "rated": str(bool(rated)).lower(),
            "time": str(time_minutes),
            "increment": str(increment),
        }
        response = self._open_stream(
            "POST", f"{self._api_url}/api/board/seek", data=data
        )
        if response is None:
            # Sem isto a aplicação ficaria esperando um oponente que nunca
            # viria, até estourar o --lichess-timeout.
            self._seek_error = (
                "O Lichess recusou o seek — veja o erro HTTP no log acima."
            )
            logger.error("Não foi possível publicar o seek.")
            return

        # O corpo é só keep-alive; o que importa é manter a conexão viva.
        for _ in self._iter_ndjson(response):
            pass
        logger.info("Seek encerrado pelo servidor (partida encontrada ou timeout).")

    def challenge_ai(
        self,
        level: int = 3,
        time_minutes: int = LICHESS_TIME_MINUTES,
        increment: int = LICHESS_INCREMENT,
        color: str = "random",
    ) -> dict:
        """Desafia a engine hospedada no Lichess (Stockfish do servidor).

        Útil para testar a integração sem precisar de um segundo jogador: a
        partida começa imediatamente e é jogável pela Board API.

        Args:
            level: Nível da IA, de 1 a 8.
            time_minutes: Tempo inicial em minutos.
            increment: Incremento por jogada em segundos.
            color: Cor desejada ('white', 'black' ou 'random').

        Returns:
            Dicionário da partida criada (contém `id`).

        Raises:
            LichessError: Se o Lichess recusar o desafio.
        """
        data = {
            "level": str(level),
            "clock.limit": str(int(time_minutes * 60)),
            "clock.increment": str(increment),
            "color": color,
        }
        logger.info(
            "Desafiando a IA do Lichess: nível %d, %d+%d, cor %s",
            level, time_minutes, increment, color,
        )

        try:
            response = self._session.post(
                f"{self._api_url}/api/challenge/ai",
                data=data,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise LichessError(f"Erro ao desafiar a IA: {exc}") from exc

        if response.status_code == 401:
            raise LichessError(
                "Token sem permissão para criar desafios. O modo --lichess-ai "
                "exige o escopo 'challenge:write' além de 'board:play'."
            )
        if not response.ok:
            raise LichessError(
                f"Lichess recusou o desafio à IA: HTTP {response.status_code} — "
                f"{response.text[:200]}"
            )

        game = response.json()
        self._game_id = game.get("id")
        # A resposta traz a cor do desafiante quando ela não foi sorteada.
        if color in ("white", "black"):
            self._player_color = color
        logger.info("Partida contra a IA criada: %s", self._game_id)
        return game

    def create_challenge(
        self,
        username: str,
        time_minutes: int = LICHESS_TIME_MINUTES,
        increment: int = LICHESS_INCREMENT,
        rated: bool = False,
        color: str = "random",
    ) -> dict:
        """Desafia uma conta específica.

        Diferente do seek, aqui dá para escolher o oponente e a cor. A partida
        só começa quando o outro lado aceitar, o que é anunciado como
        `gameStart` no stream da conta.

        Args:
            username: Conta a desafiar.
            time_minutes: Tempo inicial em minutos.
            increment: Incremento por jogada em segundos.
            rated: Se a partida é ranqueada.
            color: Cor desejada ('white', 'black' ou 'random').

        Returns:
            Dicionário do desafio criado (contém `id` e `url`).

        Raises:
            LichessError: Se o Lichess recusar o desafio.
        """
        data = {
            "rated": str(bool(rated)).lower(),
            "clock.limit": str(int(time_minutes * 60)),
            "clock.increment": str(increment),
            "color": color,
        }
        logger.info(
            "Desafiando %s: %d+%d, rated=%s, cor %s",
            username, time_minutes, increment, rated, color,
        )

        try:
            response = self._session.post(
                f"{self._api_url}/api/challenge/{username}",
                data=data,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise LichessError(f"Erro ao criar o desafio: {exc}") from exc

        if response.status_code == 401:
            raise LichessError(
                "Token sem permissão para criar desafios. "
                "--lichess-challenge exige o escopo 'challenge:write'."
            )
        if response.status_code == 404:
            raise LichessError(f"Conta '{username}' não existe no Lichess.")
        if not response.ok:
            raise LichessError(
                f"Lichess recusou o desafio a '{username}': "
                f"HTTP {response.status_code} — {response.text[:200]}"
            )

        payload = response.json()
        challenge = payload.get("challenge") or payload
        self._pending_challenge_id = challenge.get("id")
        logger.info(
            "Desafio criado: %s", challenge.get("url", self._pending_challenge_id)
        )
        return challenge

    def cancel_challenge(self, challenge_id: Optional[str] = None) -> bool:
        """Cancela um desafio ainda não aceito."""
        cid = challenge_id or self._pending_challenge_id
        if not cid:
            return False
        try:
            response = self._session.post(
                f"{self._api_url}/api/challenge/{cid}/cancel",
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException:
            return False
        if response.ok:
            logger.info("Desafio %s cancelado.", cid)
        return response.ok

    def _maybe_accept_challenge(self, event: dict) -> None:
        """Aceita um desafio recebido enquanto se espera uma partida.

        Os desafios que a própria conta enviou também aparecem neste stream —
        aceitar o próprio desafio seria um erro, daí a checagem de direção.
        """
        challenge = event.get("challenge") or {}
        challenge_id = challenge.get("id")
        challenger = challenge.get("challenger") or {}

        if not challenge_id:
            return
        if challenge.get("direction") == "out" or challenger.get("id") == self.account_id:
            logger.debug("Desafio próprio ignorado: %s", challenge_id)
            return

        name = challenger.get("name") or challenger.get("id") or "alguém"
        logger.info("Desafio recebido de %s — aceitando.", name)
        self.accept_challenge(challenge_id)

    def accept_challenge(self, challenge_id: str) -> bool:
        """Aceita um desafio recebido.

        Args:
            challenge_id: ID do desafio.

        Returns:
            True se o Lichess aceitou a operação.
        """
        try:
            response = self._session.post(
                f"{self._api_url}/api/challenge/{challenge_id}/accept",
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.error("Erro ao aceitar o desafio %s: %s", challenge_id, exc)
            return False

        if response.ok:
            logger.info("Desafio aceito: %s", challenge_id)
            return True
        logger.warning(
            "Não foi possível aceitar o desafio %s: HTTP %d",
            challenge_id, response.status_code,
        )
        return False

    # -- partida em andamento ----------------------------------------------

    def set_game_id(self, game_id: str) -> None:
        """Define manualmente a partida a acompanhar (opção --lichess-game)."""
        self._game_id = game_id

    def send_move(self, move_uci: str, game_id: Optional[str] = None) -> bool:
        """Envia uma jogada para a partida atual.

        Args:
            move_uci: Jogada em notação UCI (ex: 'e2e4', 'e7e8q').
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
            response = self._session.post(url, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            logger.error("Erro ao enviar jogada: %s", exc)
            return False

        if response.ok:
            logger.info("Jogada aceita pelo Lichess.")
            return True

        logger.warning(
            "Jogada rejeitada — Status: %d, Resposta: %s",
            response.status_code, response.text[:200],
        )
        return False

    def start_game_stream(
        self,
        callback: Callable[[dict], None],
        game_id: Optional[str] = None,
    ) -> None:
        """Acompanha os eventos da partida numa thread de background.

        Args:
            callback: Função chamada para cada evento recebido. Roda na thread
                do stream — a implementação deve ser thread-safe (na aplicação
                é um `Queue.put`).
            game_id: ID da partida (usa a atual se None).
        """
        self._spawn("LichessGameStream", self._run_game_stream, callback, game_id)

    def _run_game_stream(
        self,
        callback: Callable[[dict], None],
        game_id: Optional[str],
    ) -> None:
        """Loop de leitura do stream da partida."""
        try:
            for event in self.stream_game_events(game_id):
                callback(event)
        except Exception as exc:  # noqa: BLE001 — a thread não pode morrer calada
            logger.error("Erro no stream da partida: %s", exc, exc_info=True)
        logger.info("Stream da partida encerrado.")

    def stream_game_events(
        self,
        game_id: Optional[str] = None,
    ) -> Generator[dict, None, None]:
        """Gera eventos do jogo via stream HTTP (NDJSON).

        Args:
            game_id: ID da partida (usa a atual se None).

        Yields:
            Dicionários com eventos do jogo. Tipos principais:
            - gameFull: Estado completo (sempre o primeiro do stream)
            - gameState: Atualização (nova jogada, fim de partida, empate)
            - chatLine: Mensagem no chat
            - opponentGone: Oponente saiu da página
        """
        gid = game_id or self._game_id
        if not gid:
            logger.error("Nenhuma partida ativa para stream.")
            return

        logger.info("Abrindo stream da partida: %s", gid)
        response = self._open_stream(
            "GET", f"{self._api_url}/api/board/game/stream/{gid}"
        )
        if response is None:
            return
        yield from self._iter_ndjson(response)

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
                f"{self._api_url}/api/board/game/{gid}/resign",
                timeout=REQUEST_TIMEOUT,
            )
            return response.ok
        except requests.RequestException as exc:
            logger.error("Erro ao desistir: %s", exc)
            return False

    # -- encerramento -------------------------------------------------------

    def close(self) -> None:
        """Encerra o cliente, fecha os streams e libera as threads."""
        if not self._running:
            return

        # Antes de derrubar a sessão: um desafio nunca aceito ficaria pendurado
        # na conta, esperando um oponente que não vem mais.
        if self._pending_challenge_id:
            self.cancel_challenge()

        self._running = False

        # Fechar a resposta desbloqueia a thread parada no iter_lines().
        with self._lock:
            streams, self._streams = self._streams, []
            threads, self._threads = self._threads, []

        for response in streams:
            self._force_close(response)

        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=2)

        # As threads são daemon: se alguma ficou presa, fechar a sessão junto
        # com ela travaria o encerramento. Melhor vazar o socket e sair.
        if any(thread.is_alive() for thread in threads):
            logger.warning("Stream do Lichess não encerrou a tempo; seguindo.")
        else:
            self._session.close()

        logger.info("Cliente Lichess encerrado.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
