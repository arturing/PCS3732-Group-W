# ♚ Tabuleiro de Xadrez Eletrônico — Camada Python

Aplicação em Python para o tabuleiro de xadrez eletrônico com Raspberry Pi.
Permite jogar contra o Stockfish (engine de xadrez) ou contra oponentes
online via Lichess Board API.

## Arquitetura

O sistema é dividido em duas camadas:

| Camada | Linguagem | Responsabilidade |
|--------|-----------|-----------------|
| **Hardware/Low-Level** | C (ou mock Python) | Varredura da matriz 8×8 de reed switches, debouncing, detecção de mudanças |
| **Aplicação** | Python | Lógica do jogo, validação, interface com engines, GUI |

A comunicação entre as camadas é feita via IPC (subprocess stdout/stdin, Named Pipe ou stdin).

### Módulos Python

```
app/
├── config.py            # Configurações e constantes
├── ipc_reader.py        # Leitor de eventos IPC (pipe/stdin/subprocess)
├── move_interpreter.py  # Interpreta eventos de sensor → jogadas de xadrez
├── game_state.py        # Motor de estado do jogo (python-chess)
├── stockfish_engine.py  # Interface UCI com Stockfish
├── lichess_client.py    # Cliente da Lichess Board API
├── gui.py               # Interface gráfica com pygame
└── main.py              # Ponto de entrada
```

```
mock/
└── hardware_mock.py     # Simulação do processo C para testes
```

## Instalação

### Pré-requisitos

- Python 3.10+
- Stockfish (para modo offline)

### Instalar dependências

```bash
pip install -r requirements.txt
```

### Instalar Stockfish

**Linux (Raspberry Pi / Ubuntu):**
```bash
sudo apt install stockfish
```

**Windows:**
Baixe de https://stockfishchess.org/download/ e configure o caminho:
```bash
set CHESS_STOCKFISH_PATH=C:\caminho\para\stockfish.exe
```

## Uso

### Jogar contra Stockfish (com mock do hardware)

```bash
python -m app.main --mode stockfish
```

O mock interativo será aberto automaticamente. Digite jogadas no formato
UCI (ex: `e2e4`) no terminal para simular movimentos no tabuleiro.

### Opções de linha de comando

```
python -m app.main --help

Opções:
  --mode {stockfish,lichess}   Modo de jogo (padrão: stockfish)
  --color {white,black}        Cor do jogador (padrão: white)
  --ipc {subprocess,stdin,pipe} Modo de IPC (padrão: subprocess)
  --stockfish-path PATH        Caminho do Stockfish
  --stockfish-time SECONDS     Tempo de cálculo (padrão: 1.0)
  --token TOKEN                Token Lichess (modo lichess)
  --flip                       Inverte o tabuleiro
  --no-gui                     Sem interface gráfica
  --log-level LEVEL            Nível de log
```

### Jogar contra Lichess (online)

1. Obtenha um token de API em https://lichess.org/account/oauth/token
2. Execute:
```bash
python -m app.main --mode lichess --token lip_seu_token
```

### Usar o Mock diretamente

O mock pode ser executado standalone para testes:

```bash
# Modo interativo
python -m mock.hardware_mock --mode interactive

# Modo automático (jogadas aleatórias)
python -m mock.hardware_mock --mode auto --auto-moves 30

# Modo scripted (sequência pré-definida)
python -m mock.hardware_mock --mode scripted --moves e2e4 e7e5 g1f3 b8c6
```

#### Comandos do mock interativo

| Comando | Descrição |
|---------|-----------|
| `e2e4` | Simula movimento do jogador (gera evento IPC) |
| `opp e7e5` | Aplica movimento do oponente (sem evento) |
| `board` | Exibe estado dos sensores |
| `chess` | Exibe tabuleiro completo |
| `legal` | Lista movimentos legais |
| `fen` | Exibe FEN atual |
| `auto` | Joga partida automática |
| `quit` | Encerrar |

## Protocolo IPC

A comunicação entre o processo C (ou mock) e o Python usa um protocolo
simples baseado em texto:

```
casa:estado,casa:estado\n
```

- **casa**: Notação algébrica (a1–h8)
- **estado**: `0` (desocupada) ou `1` (ocupada)
- Exemplo: `e2:0,e4:1\n` — peça saiu de e2, chegou em e4

### Exemplos de eventos

| Jogada | Evento IPC |
|--------|-----------|
| e2→e4 (peão) | `e2:0,e4:1` |
| O-O (roque curto brancas) | `e1:0,g1:1,h1:0,f1:1` |
| O-O-O (roque longo) | `e1:0,c1:1,a1:0,d1:1` |
| Captura (Bxf7) | `c4:0,f7:1` |

## Configuração via variáveis de ambiente

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `CHESS_IPC_MODE` | Modo IPC | `subprocess` |
| `CHESS_PIPE_PATH` | Caminho do Named Pipe | `/tmp/chess_board_pipe` |
| `CHESS_STOCKFISH_PATH` | Binário do Stockfish | `stockfish` |
| `CHESS_STOCKFISH_TIME` | Tempo de cálculo (s) | `1.0` |
| `CHESS_STOCKFISH_DEPTH` | Profundidade de busca | (sem limite) |
| `CHESS_STOCKFISH_SKILL` | Nível de habilidade (0-20) | (não configurado) |
| `CHESS_LICHESS_TOKEN` | Token OAuth2 Lichess | (vazio) |
| `CHESS_BOARD_SIZE` | Tamanho do tabuleiro (px) | `640` |

## Teclas de Atalho (GUI)

| Tecla | Ação |
|-------|------|
| `F` | Inverter tabuleiro |
| `ESC` | Fechar aplicação |
| `Q/R/B/N` | Selecionar peça de promoção |

## Compatibilidade

| Plataforma | IPC subprocess | IPC stdin | IPC pipe (FIFO) | GUI |
|------------|:-:|:-:|:-:|:-:|
| Linux / Raspberry Pi | ✅ | ✅ | ✅ | ✅ |
| Windows | ✅ | ✅ | ❌ | ✅ |
| macOS | ✅ | ✅ | ✅ | ✅ |
