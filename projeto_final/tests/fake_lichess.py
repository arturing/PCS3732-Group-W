"""Servidor falso que imita os endpoints da Lichess Board API usados pelo app."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GAME_ID = "testgame"

# Respostas da "IA" depois de cada lance do jogador
REPLIES = ["e7e5", "b8c6", "g8f6"]


class State:
    def __init__(self):
        self.moves: list[str] = []
        self.game_started = threading.Event()
        self.state_updates: list[dict] = []
        self.cond = threading.Condition()
        self.seek_opened = threading.Event()
        self.status = "started"
        self.winner = None
        self.accepted = []
        self.cancelled = []

    def push_move(self, uci):
        with self.cond:
            self.moves.append(uci)
            reply_index = len(self.moves) // 2
            if reply_index <= len(REPLIES) and len(self.moves) % 2 == 1:
                self.moves.append(REPLIES[reply_index - 1] if reply_index else REPLIES[0])
            self.cond.notify_all()

    def finish(self, status, winner=None):
        with self.cond:
            self.status = status
            self.winner = winner
            self.cond.notify_all()


STATE = State()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    # -- helpers --

    def _json(self, payload, code=200):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _open_ndjson(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

    def _chunk(self, text):
        data = text.encode()
        self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")
        self.wfile.flush()

    def _emit(self, obj):
        self._chunk(json.dumps(obj) + "\n")

    # -- rotas --

    def do_GET(self):
        if self.path == "/api/account":   # AUTH_CHECK
            auth = self.headers.get("Authorization", "")
            if auth != "Bearer faketoken123":
                return self._json({"error": "No such token"}, 401)
            return self._json({"id": "tester", "username": "Tester"})

        if self.path == "/api/stream/event":
            self._open_ndjson()
            self._emit({
                "type": "challenge",
                "challenge": {"id": "outgoing1", "direction": "out",
                              "challenger": {"id": "tester", "name": "Tester"}},
            })
            self._emit({
                "type": "challenge",
                "challenge": {"id": "incoming1", "direction": "in",
                              "challenger": {"id": "adversario", "name": "Adversario"}},
            })
            STATE.seek_opened.wait(timeout=10)
            time.sleep(0.1)
            self._emit({
                "type": "gameStart",
                "game": {"gameId": GAME_ID, "color": "white", "isMyTurn": True},
            })
            STATE.game_started.set()
            for _ in range(40):
                self._chunk("\n")   # keep-alive
                time.sleep(0.25)
            return

        if self.path == f"/api/board/game/stream/{GAME_ID}":
            self._open_ndjson()
            self._emit({
                "type": "gameFull",
                "id": GAME_ID,
                "initialFen": "startpos",
                "white": {"id": "tester", "name": "Tester", "rating": 1500},
                "black": {"aiLevel": 3},
                "state": {
                    "type": "gameState", "moves": "",
                    "status": "started", "wtime": 600000, "btime": 600000,
                },
            })
            seen = 0
            last_status = "started"
            while True:
                with STATE.cond:
                    STATE.cond.wait(timeout=0.5)
                    moves = list(STATE.moves)
                    status, winner = STATE.status, STATE.winner
                if len(moves) != seen or status != last_status:
                    seen, last_status = len(moves), status
                    payload = {
                        "type": "gameState", "moves": " ".join(moves),
                        "status": status,
                    }
                    if winner:
                        payload["winner"] = winner
                    self._emit(payload)
                    if status != "started":
                        return
                else:
                    self._chunk("\n")
            return

        self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/api/board/seek":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode()
            # Como o Lichess de verdade: /api/board/seek nao aceita "color"
            if "color=" in body:
                return self._json(
                    {"error": {"color": ["Unexpected field"]}}, 400)
            if "time=999" in body:
                return self._json({"error": {"time": ["Invalid"]}}, 400)
            self._open_ndjson()
            STATE.seek_opened.set()
            # long-polling: só keep-alive até a partida começar
            STATE.game_started.wait(timeout=10)
            time.sleep(0.2)
            return

        if self.path.startswith(f"/api/board/game/{GAME_ID}/move/"):
            uci = self.path.rsplit("/", 1)[-1]
            if uci == "a1a8":          # lance que o "servidor" recusa
                return self._json({"error": "Not a legal move"}, 400)
            STATE.push_move(uci)
            return self._json({"ok": True})

        if self.path.endswith("/cancel"):
            STATE.cancelled.append(self.path.split("/")[-2])
            return self._json({"ok": True})

        if self.path == "/api/challenge/adversario":
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            STATE.seek_opened.set()
            return self._json({"id": GAME_ID, "url": f"https://lichess.org/{GAME_ID}",
                               "status": "created"})

        if self.path == "/api/challenge/naoexiste":
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            return self._json({"error": "No such user"}, 404)

        if self.path.startswith("/api/challenge/") and self.path.endswith("/accept"):
            STATE.accepted.append(self.path.split("/")[-2])
            STATE.seek_opened.set()
            return self._json({"ok": True})

        if self.path.startswith("/api/challenge/ai"):
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            STATE.seek_opened.set()
            return self._json({"id": GAME_ID})

        self._json({"error": "not found"}, 404)


def serve():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


if __name__ == "__main__":
    # Modo standalone: `python tests/fake_lichess.py 8777` sobe o servidor
    # numa porta fixa, para testar a aplicação de verdade contra ele.
    import sys

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8777
    print(f"Servidor falso do Lichess em http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
