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
├── hardware_mock.py     # Simulação do processo C para testes
└── gui_mock.py          # GUI do mock: matriz 8×8 de botões (reed switches)
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

O mock do hardware é aberto automaticamente numa segunda janela: uma matriz
8×8 de botões, um por casa. Cada botão representa um reed switch — clique
para alternar entre pressionado (peça detectada) e solto (casa vazia).

Para simular a jogada `e2e4`, clique em `e2` (a peça sai) e depois em `e4`
(a peça chega) — a mesma sequência de dois eventos que o hardware real
produziria. Se não houver display disponível, o mock cai automaticamente
para o modo interativo por terminal.

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
# Modo GUI — matriz de botões na tela (padrão)
python -m mock.hardware_mock

# Modo GUI com o tabuleiro invertido (útil jogando de pretas)
python -m mock.hardware_mock --color black --flip

# Modo interativo (comandos no terminal)
python -m mock.hardware_mock --mode interactive

# Modo automático (jogadas aleatórias)
python -m mock.hardware_mock --mode auto --auto-events 30

# Modo scripted (sequência pré-definida)
python -m mock.hardware_mock --mode scripted --moves e2e4 e7e5 g1f3 b8c6
```

#### Mock em modo GUI

Cada casa é um botão que reflete o estado do seu reed switch:

| Aparência | Significado |
|-----------|-------------|
| Afundado, com LED verde | Sensor ativo — ímã/peça detectada |
| Em relevo, sem LED | Sensor inativo — casa vazia |

| Interação | Ação |
|-----------|------|
| Clique numa casa | Alterna o sensor e envia o evento IPC |
| Arrastar com o botão pressionado | Aplica o mesmo estado às casas percorridas |
| `Reset` / `R` | Volta os sensores ao estado inicial |
| `Limpar` / `C` | Desliga todos os sensores |
| `Inverter` / `F` | Inverte a orientação do tabuleiro |
| `Sair` / `Esc` / `Q` | Encerra o mock |

A barra inferior mostra o último evento enviado por stdout e a contagem de
sensores ativos. O tamanho do tabuleiro é ajustável por
`CHESS_MOCK_BOARD_SIZE`.

#### Comandos do mock interativo

| Comando | Descrição |
|---------|-----------|
| `e2e4` | Simula movimento (origem→destino, gera evento IPC) |
| `on e4` | Ativa o sensor em e4 (coloca peça) |
| `off e4` | Desativa o sensor em e4 (remove peça) |
| `board` | Exibe estado dos sensores |
| `reset` | Volta ao estado inicial |
| `help` | Lista os comandos |
| `quit` | Encerrar |

## Destaques no tabuleiro

Enquanto o jogador está com uma peça na mão — o sensor da casa desligou e
nenhum outro ligou — a GUI mostra para onde essa peça pode ir:

| Marca | Significado |
|-------|-------------|
| Casa verde | Casa de onde a peça foi levantada |
| Ponto no centro | Destino legal, casa livre |
| Anel vermelho | Destino legal que captura uma peça (inclui *en passant*) |
| Casa amarela | Origem e destino do último lance |

Os destinos saem dos lances legais do tabuleiro virtual, então já consideram
xeque e peças cravadas: uma peça sem lance legal não recebe marca nenhuma.
Nada é destacado fora do turno do jogador, nem quando a peça foi levantada
para desfazer um movimento ilegal — aí o que vale é a instrução da barra de
status.

## Roque em duas etapas

No tabuleiro físico ninguém move rei e torre ao mesmo tempo, então o roque é
feito **em duas etapas, o rei primeiro**:

1. **Mova o rei duas casas** (e1→g1 ou e1→c1). Sozinho, esse lance não existe
   nas regras — aqui ele é lido como o começo de um roque. O tabuleiro
   virtual **não** é atualizado ainda; a barra de status passa a pedir a
   torre e a GUI destaca a casa dela e o destino.
2. **Mova a torre** para o outro lado do rei (h1→f1 ou a1→d1). Só agora o
   roque é aplicado ao tabuleiro virtual, como um lance só.

| Estado | Mensagem exibida |
|--------|------------------|
| Rei no lugar, torre ainda na casa dela | `Roque — agora mova a torre de h1 para f1` |
| Torre na mão | `Roque — coloque a torre em f1` |
| Rei levantado de novo | `Roque — coloque o rei em g1` |

Enquanto o roque está pela metade:

- **Devolver o rei à casa dele cancela o roque.** Nada é aplicado e o jogo
  volta ao estado anterior.
- **Nenhum outro lance é aceito.** Mexer noutra peça faz a barra de status
  pedir a correção; o roque só se completa com o resto do tabuleiro na
  posição, como qualquer outro lance.

O evento único com as quatro mudanças (`e1:0,g1:1,h1:0,f1:1`) continua
valendo: se a torre já estiver no lugar quando o rei for reconhecido, o roque
é aplicado na hora, sem espera.

## Instruções na barra de status

A barra inferior da GUI diz o que fazer **no tabuleiro físico** para que ele
volte à posição que o jogo espera. A instrução tem prioridade sobre qualquer
outra mensagem enquanto o tabuleiro estiver diferente do esperado.

Uma instrução por vez, na ordem do que precisa ser feito: a peça que está na
mão, as peças deslocadas (que bloqueiam o jogo) e depois a diferença nos
sensores.

| Situação nos sensores | Mensagem exibida |
|-----------------------|------------------|
| Uma peça foi levantada | `Peça de e2 na mão — solte no destino` |
| Peça capturada pelo oponente ainda no tabuleiro | `Remova a peça de d5` |
| Movimento ilegal (registrado no histórico) | `Desfaça o movimento ilegal — mova a peça de e5 para e2` |
| Lance tentado com o tabuleiro fora da posição | `Arrume o tabuleiro antes de jogar (2 pendentes) — mova a peça de f3 para g1` |
| Peça deslocada na mão | `Desfaça o movimento ilegal — coloque a peça em e2` |
| Casas erradas sem par conhecido | `Tabuleiro fora de sincronia — remova de f1, g1 e coloque em e1, h1` |
| Tudo no lugar novamente | `Tabuleiro na posição certa — sua vez` |

Avisos do jogo entram como prefixo (`Xeque! Remova a peça de e2`). As mesmas
instruções vão para o log, o que as torna visíveis também com `--no-gui`.

### Histórico de peças deslocadas

Quando o tabuleiro virtual recusa um lance, o par origem→destino é guardado
num histórico de peças deslocadas. Isso tem duas consequências:

- **O jogo fica bloqueado até o tabuleiro voltar à posição.** Enquanto houver
  peça deslocada, nenhum lance novo é aplicado: a peça movida também entra no
  histórico (como `bloqueado`) e recebe sua própria instrução de devolução. As
  devoluções são pedidas da mais recente para a mais antiga — a peça mais nova
  pode estar justamente na casa de origem de uma anterior.
- **A instrução nunca inventa emparelhamento.** `mova a peça de X para Y` só
  é dito quando X e Y foram registrados juntos, no momento do lance ilegal.
  Para uma diferença qualquer nos sensores, a instrução é `remova de ... e
  coloque em ...`: os reed switches dizem *onde* há ímã, não *qual* peça é, e
  um palpite errado mandaria pôr a peça numa casa que, no tabuleiro virtual, é
  de outra — criando a dessincronia que a instrução deveria corrigir.

O registro é descartado quando não há mais para onde voltar — o oponente
capturou a peça deslocada, ou o jogador já pôs outra peça na casa de origem.
Nos dois casos a instrução passa a ser só `remova a peça de e5`.

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
| O-O (roque curto brancas) | `e1:0,g1:1` e depois `h1:0,f1:1` |
| O-O-O (roque longo) | `e1:0,c1:1` e depois `a1:0,d1:1` |
| Captura (Bxf7) | `c4:0,f7:1` |

O roque também é aceito num evento só (`e1:0,g1:1,h1:0,f1:1`), mas na mão do
jogador ele chega em duas etapas — veja [Roque em duas
etapas](#roque-em-duas-etapas).

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
| `CHESS_MOCK_BOARD_SIZE` | Tamanho da matriz de botões do mock (px) | `560` |

## Teclas de Atalho

### GUI da aplicação

| Tecla | Ação |
|-------|------|
| `F` | Inverter tabuleiro |
| `ESC` | Fechar aplicação |
| `Q/R/B/N` | Selecionar peça de promoção |

### GUI do mock (matriz de botões)

| Tecla | Ação |
|-------|------|
| `R` | Reset dos sensores |
| `C` | Limpar (desliga todos) |
| `F` | Inverter tabuleiro |
| `ESC` / `Q` | Encerrar o mock |

## Compatibilidade

| Plataforma | IPC subprocess | IPC stdin | IPC pipe (FIFO) | GUI |
|------------|:-:|:-:|:-:|:-:|
| Linux / Raspberry Pi | ✅ | ✅ | ✅ | ✅ |
| Windows | ✅ | ✅ | ❌ | ✅ |
| macOS | ✅ | ✅ | ✅ | ✅ |
