"""
hardware_mock.py — Mock do Processo C / Hardware para testes.

Simula o comportamento do processo C que lê a matriz 8×8 de reed switches.
Este mock é BURRO — assim como o hardware real, ele não sabe nada sobre
regras de xadrez, movimentos legais ou turnos. Ele apenas:

  1. Mantém um grid 8×8 de sensores (ocupado / vazio)
  2. Permite ao usuário alterar o estado das casas
  3. Envia as mudanças via stdout no formato IPC

Modos de operação:
  - gui         : matriz de 64 botões na tela (padrão) — ver gui_mock.py
  - interactive : comandos digitados no terminal
  - auto        : eventos aleatórios
  - scripted    : sequência pré-definida de movimentos

Protocolo de saída (stdout):
    casa:estado,casa:estado\n
    Exemplo: "e2:0,e4:1\n"

Comunicação de log/prompts: stderr (não interfere no IPC).

Compatibilidade: Windows e Linux.
"""

import sys
import time
import signal
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
    stream=sys.stderr,  # Log vai para stderr, eventos vão para stdout
)
logger = logging.getLogger("hardware_mock")

# ---------------------------------------------------------------------------
#  Constantes do tabuleiro
# ---------------------------------------------------------------------------

FILES = "abcdefgh"
RANKS = "12345678"


def square_valid(name: str) -> bool:
    """Verifica se o nome de casa é válido (ex: 'e4')."""
    return len(name) == 2 and name[0] in FILES and name[1] in RANKS


# ---------------------------------------------------------------------------
#  Mock dos Sensores
# ---------------------------------------------------------------------------

class SensorGrid:
    """Simulação da matriz 8×8 de reed switches.

    Cada célula é True (ímã detectado / peça presente) ou False (vazio).
    O grid não sabe NADA sobre xadrez — é puramente um array de booleanos,
    assim como os reed switches reais.
    """

    def __init__(self):
        # Grid 8×8 inicializado como vazio
        self.state: dict[str, bool] = {}
        for f in FILES:
            for r in RANKS:
                self.state[f"{f}{r}"] = False

    def set_initial_position(self, occupied_ranks: list[str]) -> None:
        """Define quais fileiras começam com peças (sensores ativados).

        Args:
            occupied_ranks: Lista de ranks com peças (ex: ["1", "2"]
                            para as brancas nas fileiras 1 e 2).
        """
        for f in FILES:
            for r in RANKS:
                sq = f"{f}{r}"
                self.state[sq] = r in occupied_ranks

    def get(self, square: str) -> bool:
        """Lê o estado de um sensor."""
        return self.state.get(square, False)

    def set(self, square: str, value: bool) -> None:
        """Define o estado de um sensor."""
        self.state[square] = value

    def apply_move(self, from_sq: str, to_sq: str) -> dict[str, int]:
        """Simula mover uma peça: origem fica vazia, destino fica ocupado.

        Returns:
            Dicionário de mudanças {casa: estado}.
        """
        changes: dict[str, int] = {}

        if self.state.get(from_sq, False):
            self.state[from_sq] = False
            changes[from_sq] = 0

        self.state[to_sq] = True
        changes[to_sq] = 1

        return changes

    def remove_piece(self, square: str) -> dict[str, int]:
        """Remove uma peça (sensor desativa)."""
        changes: dict[str, int] = {}
        if self.state.get(square, False):
            self.state[square] = False
            changes[square] = 0
        return changes

    def place_piece(self, square: str) -> dict[str, int]:
        """Coloca uma peça (sensor ativa)."""
        changes: dict[str, int] = {}
        if not self.state.get(square, False):
            self.state[square] = True
            changes[square] = 1
        return changes

    def display(self) -> str:
        """Representação visual do grid de sensores."""
        lines = []
        lines.append("  a b c d e f g h   (Sensores)")
        lines.append("  ─────────────────")
        for r in reversed(RANKS):
            row = f"{r}|"
            for f in FILES:
                sq = f"{f}{r}"
                row += " ●" if self.state[sq] else " ·"
            row += f" |{r}"
            lines.append(row)
        lines.append("  ─────────────────")
        lines.append("  a b c d e f g h")
        lines.append("")
        lines.append("  ● = peça detectada    · = vazio")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
#  Funções de comunicação IPC
# ---------------------------------------------------------------------------

def send_event(changes: dict[str, int]) -> None:
    """Envia um evento de mudança para stdout (lido pelo processo Python).

    Args:
        changes: Dicionário {casa: estado} com as mudanças.
    """
    if not changes:
        return
    event = ",".join(f"{sq}:{state}" for sq, state in changes.items())
    sys.stdout.write(event + "\n")
    sys.stdout.flush()
    logger.info("Evento IPC enviado: %s", event)


def parse_move_input(cmd: str) -> tuple[str, str] | None:
    """Parseia input no formato UCI (ex: 'e2e4') em (origem, destino).

    Returns:
        Tupla (from_sq, to_sq) ou None se inválido.
    """
    cmd = cmd.strip().lower()
    if len(cmd) == 4 and square_valid(cmd[:2]) and square_valid(cmd[2:]):
        return cmd[:2], cmd[2:]
    # Promoção (ex: e7e8q) — ignora a letra de promoção
    if len(cmd) == 5 and square_valid(cmd[:2]) and square_valid(cmd[2:4]):
        return cmd[:2], cmd[2:4]
    return None


# ---------------------------------------------------------------------------
#  Modos de execução
# ---------------------------------------------------------------------------

def run_gui(occupied_ranks: list[str], flip: bool = False) -> bool:
    """Modo GUI: matriz de 64 botões na tela, um por casa do tabuleiro.

    Cada botão fica pressionado (sensor ativo) ou solto (casa vazia).
    Clicar alterna o sensor e emite o evento IPC correspondente.

    Args:
        occupied_ranks: Fileiras inicialmente ocupadas.
        flip: Se True, desenha o tabuleiro invertido (fileira 1 no topo).

    Returns:
        True se a GUI rodou; False se ela não está disponível (pygame
        ausente ou sem display), caso em que o chamador pode cair no
        modo interativo.
    """
    # O mock roda tanto como módulo (`python -m mock.hardware_mock`) quanto
    # como script (`python mock/hardware_mock.py`, como faz o ipc_reader).
    # Os dois casos têm sys.path diferentes, daí as duas formas de import.
    try:
        try:
            from mock.gui_mock import SensorBoardGUI, GUIUnavailable
        except ImportError:
            from gui_mock import SensorBoardGUI, GUIUnavailable
    except ImportError as exc:
        logger.warning("GUI indisponível (%s).", exc)
        return False

    grid = SensorGrid()
    grid.set_initial_position(occupied_ranks)

    ranks_desc = ", ".join(occupied_ranks)
    logger.info(
        "Modo GUI — fileiras com peças: %s. Eventos IPC vão para stdout.",
        ranks_desc,
    )

    gui = SensorBoardGUI(
        grid,
        send_event,
        initial_state=dict(grid.state),
        flip=flip,
        info=f"peças nas fileiras {ranks_desc}  ·  eventos -> stdout",
    )

    try:
        gui.run()
    except GUIUnavailable as exc:
        logger.warning("GUI indisponível (%s).", exc)
        return False
    except KeyboardInterrupt:
        pass

    print("Mock encerrado.", file=sys.stderr)
    return True


def run_interactive(occupied_ranks: list[str]) -> None:
    """Modo interativo: o usuário digita comandos no terminal.

    Comandos:
        e2e4         — Move peça (e2 vira vazio, e4 vira ocupado)
        on e4        — Ativa sensor em e4 (coloca peça)
        off e4       — Desativa sensor em e4 (remove peça)
        board        — Exibe estado dos sensores
        reset        — Volta ao estado inicial
        quit         — Encerra
    """
    grid = SensorGrid()
    grid.set_initial_position(occupied_ranks)

    ranks_desc = ", ".join(occupied_ranks)
    print(
        f"{'=' * 50}\n"
        f"  HARDWARE MOCK — Simulador de Reed Switches\n"
        f"{'=' * 50}\n"
        f"  Fileiras com peças: {ranks_desc}\n"
        f"  Eventos IPC → stdout\n"
        f"  Digite 'help' para ver comandos.\n"
        f"{'=' * 50}\n",
        file=sys.stderr,
    )
    print(grid.display(), file=sys.stderr)

    while True:
        try:
            print("\n[sensor] > ", end="", file=sys.stderr)
            sys.stderr.flush()

            line = sys.stdin.readline()
            if not line:
                break

            cmd = line.strip()
            if not cmd:
                continue

            cmd_lower = cmd.lower()

            # --- Comandos ---

            if cmd_lower in ("quit", "exit", "q"):
                break

            elif cmd_lower == "help":
                print(
                    "\nComandos:\n"
                    "  e2e4       — Move peça (origem→destino)\n"
                    "  on e4      — Ativa sensor (coloca peça)\n"
                    "  off e4     — Desativa sensor (remove peça)\n"
                    "  board      — Estado dos sensores\n"
                    "  reset      — Volta ao estado inicial\n"
                    "  quit       — Encerrar\n",
                    file=sys.stderr,
                )

            elif cmd_lower == "board":
                print(grid.display(), file=sys.stderr)

            elif cmd_lower == "reset":
                grid.set_initial_position(occupied_ranks)
                print("✓ Sensores resetados.", file=sys.stderr)
                print(grid.display(), file=sys.stderr)

            elif cmd_lower.startswith("on "):
                sq = cmd_lower[3:].strip()
                if square_valid(sq):
                    changes = grid.place_piece(sq)
                    if changes:
                        send_event(changes)
                        print(f"✓ Sensor {sq} ativado.", file=sys.stderr)
                        print(grid.display(), file=sys.stderr)
                    else:
                        print(f"  Sensor {sq} já estava ativo.", file=sys.stderr)
                else:
                    print(f"✗ Casa inválida: {sq}", file=sys.stderr)

            elif cmd_lower.startswith("off "):
                sq = cmd_lower[4:].strip()
                if square_valid(sq):
                    changes = grid.remove_piece(sq)
                    if changes:
                        send_event(changes)
                        print(f"✓ Sensor {sq} desativado.", file=sys.stderr)
                        print(grid.display(), file=sys.stderr)
                    else:
                        print(f"  Sensor {sq} já estava inativo.", file=sys.stderr)
                else:
                    print(f"✗ Casa inválida: {sq}", file=sys.stderr)

            else:
                # Tenta interpretar como movimento (ex: e2e4)
                parsed = parse_move_input(cmd_lower)
                if parsed:
                    from_sq, to_sq = parsed
                    if not grid.get(from_sq):
                        print(
                            f"⚠ Sensor {from_sq} está vazio — "
                            f"nenhuma peça para mover. Enviando mesmo assim.",
                            file=sys.stderr,
                        )
                    changes = grid.apply_move(from_sq, to_sq)
                    send_event(changes)
                    print(
                        f"✓ {from_sq} → {to_sq}",
                        file=sys.stderr,
                    )
                    print(grid.display(), file=sys.stderr)
                else:
                    print(
                        f"✗ Comando não reconhecido: '{cmd}'. "
                        f"Use 'help' para ver opções.",
                        file=sys.stderr,
                    )

        except KeyboardInterrupt:
            print("\nEncerrando...", file=sys.stderr)
            break
        except EOFError:
            break

    print("Mock encerrado.", file=sys.stderr)


def run_auto(occupied_ranks: list[str], num_events: int = 20) -> None:
    """Modo automático: gera eventos aleatórios para teste.

    Seleciona aleatoriamente uma casa ocupada como origem e uma
    vazia como destino, simulando movimentos.
    """
    import random

    grid = SensorGrid()
    grid.set_initial_position(occupied_ranks)

    print(f"\n=== Modo Automático ({num_events} eventos) ===\n", file=sys.stderr)

    for i in range(num_events):
        occupied = [sq for sq, v in grid.state.items() if v]
        empty = [sq for sq, v in grid.state.items() if not v]

        if not occupied or not empty:
            print("Sem movimentos possíveis.", file=sys.stderr)
            break

        from_sq = random.choice(occupied)
        to_sq = random.choice(empty)

        changes = grid.apply_move(from_sq, to_sq)
        send_event(changes)
        print(f"  [{i+1}] {from_sq} → {to_sq}", file=sys.stderr)

        time.sleep(0.5)

    print("\n=== Modo automático concluído ===", file=sys.stderr)


def run_scripted(moves: list[str], occupied_ranks: list[str]) -> None:
    """Modo scripted: executa sequência pré-definida de movimentos.

    Args:
        moves: Lista de movimentos UCI (ex: ["e2e4", "d2d4"]).
        occupied_ranks: Fileiras inicialmente ocupadas.
    """
    grid = SensorGrid()
    grid.set_initial_position(occupied_ranks)

    print(f"\n=== Modo Scripted ({len(moves)} movimentos) ===\n", file=sys.stderr)

    for i, move_str in enumerate(moves):
        parsed = parse_move_input(move_str)
        if parsed:
            from_sq, to_sq = parsed
            changes = grid.apply_move(from_sq, to_sq)
            send_event(changes)
            print(f"  [{i+1}] {from_sq} → {to_sq}", file=sys.stderr)
        else:
            print(f"  [{i+1}] IGNORADO (formato inválido): {move_str}", file=sys.stderr)

        time.sleep(0.3)

    print("\n=== Modo scripted concluído ===", file=sys.stderr)


# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Mock do hardware (reed switches) do tabuleiro de xadrez.\n"
            "Simula sensores ON/OFF — NÃO conhece regras de xadrez."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--color", choices=["white", "black"], default="white",
        help="Cor das peças físicas — define quais fileiras iniciam "
             "ocupadas (padrão: white → fileiras 1,2).",
    )
    parser.add_argument(
        "--mode", choices=["gui", "interactive", "auto", "scripted"],
        default="gui",
        help="Modo de operação (padrão: gui — matriz de botões na tela; "
             "cai para interactive se não houver display).",
    )
    parser.add_argument(
        "--flip", action="store_true",
        help="Inverte o tabuleiro na GUI (fileira 1 no topo).",
    )
    parser.add_argument(
        "--moves", nargs="*", default=None,
        help="Movimentos UCI para modo scripted (ex: e2e4 d2d4).",
    )
    parser.add_argument(
        "--auto-events", type=int, default=20,
        help="Número de eventos automáticos (modo auto, padrão: 20).",
    )

    args = parser.parse_args()

    # Define quais fileiras têm peças
    if args.color == "white":
        ranks = ["1", "2"]
    else:
        ranks = ["7", "8"]

    # Ignora SIGPIPE em sistemas Unix
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    if args.mode == "gui":
        # Sem pygame ou sem display (ex: SSH sem X), usa o terminal.
        if not run_gui(ranks, flip=args.flip):
            logger.info("Caindo para o modo interativo (terminal).")
            run_interactive(ranks)
    elif args.mode == "interactive":
        run_interactive(ranks)
    elif args.mode == "auto":
        run_auto(ranks, args.auto_events)
    elif args.mode == "scripted":
        moves = args.moves or ["e2e4", "d2d4", "g1f3", "b1c3"]
        run_scripted(moves, ranks)
