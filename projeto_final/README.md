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

```
tests/
├── fake_lichess.py      # Servidor falso da Board API (testes sem token/rede)
├── test_lichess.py      # Modo Lichess: cliente e aplicação
├── test_challenge.py    # Desafios enviados e recebidos
├── test_stockfish_loop.py  # Regressão do loop principal
└── run_all.py           # Roda todas as suítes
```

```bash
python tests/run_all.py
```

## Instalação

### Pré-requisitos

- Python 3.10+
- Stockfish (para modo offline)

### Instalar dependências

```bash
pip install -r requirements.txt     # ou: make deps
```

Com Nix, nada disso é preciso: `nix develop` (na raiz do repositório) já traz
Python com as dependências, o Stockfish e as fontes das peças — veja
[Com o Nix](#com-o-nix).

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

### Atalhos do Makefile

Todos os modos de execução têm um alvo no `Makefile` da pasta `projeto_final/`.
`make` sozinho lista os alvos com os valores correntes das variáveis:

```bash
cd projeto_final
make
```

| Alvo | O que faz |
|------|-----------|
| `make stockfish` | Partida offline contra o Stockfish (não precisa de rede nem de token) |
| `make lichess-ai` | Partida contra a IA do Lichess (nível `LICHESS_LEVEL`, padrão 3) |
| `make random-sir` | Desafia a conta `random-sir` no Lichess |
| `make lichess-user OPPONENT=fulano` | Desafia a conta informada |
| `make lichess-seek` | Publica um *seek* e espera um oponente humano qualquer |
| `make lichess-game GAME=AbCdEfGh` | Retoma uma partida já em andamento na conta |
| `make mock` | Roda só o mock do hardware (sem a aplicação) |
| `make test` | Roda `tests/run_all.py` |
| `make deps` | `pip install -r requirements.txt` |
| `make shell` | Abre o devShell do Nix (`make shell-classic` para `nix-shell`) |
| `make clean` | Remove `__pycache__` e caches de ferramentas |

Os alvos do Lichess verificam antes se há um token acessível e falham com a
instrução de como criá-lo — em vez de abrir a janela e só então tomar um 401.

#### Variáveis

Qualquer alvo aceita variáveis na linha de comando, que é como o `make` passa
argumentos:

```bash
make stockfish COLOR=black STOCKFISH_TIME=2.0
make lichess-ai LICHESS_LEVEL=6 LICHESS_TIME=15
make lichess-user OPPONENT=fulano COLOR=black
make mock MOCK_MODE=interactive
```

| Variável | Padrão | Para quê |
|----------|--------|----------|
| `COLOR` | `white` | Cor das peças físicas (`white`/`black`) |
| `LOG_LEVEL` | `INFO` | Nível de log |
| `ARGS` | — | Opções extras repassadas direto ao `app.main` |
| `STOCKFISH_TIME` | `1.0` | Segundos de cálculo por lance |
| `STOCKFISH_PATH` | — | Binário do Stockfish (vazio: `$CHESS_STOCKFISH_PATH` ou o do `PATH`) |
| `LICHESS_LEVEL` | `3` | Nível da IA do Lichess (1–8) |
| `LICHESS_TIME` | `10` | Minutos iniciais |
| `LICHESS_INC` | `0` | Incremento por lance, em segundos |
| `LICHESS_TIMEOUT` | `180` | Espera máxima por um oponente, em segundos |
| `OPPONENT` | — | Conta a desafiar em `make lichess-user` |
| `GAME` | — | Id da partida em `make lichess-game` |
| `MOCK_MODE` | `gui` | Modo do mock em `make mock` |
| `PYTHON` | `python3` | Interpretador usado |
| `USE_NIX` | — | `USE_NIX=1` roda o alvo dentro do devShell do flake |

O `ARGS` cobre o que não tem variável própria — as opções da
[lista completa](#opções-de-linha-de-comando) continuam todas disponíveis:

```bash
make stockfish ARGS="--no-gui --ipc stdin"
```

#### Com o Nix

O repositório tem um `flake.nix` com Python (mais `python-chess`, `pygame` e
`requests`), Stockfish, `make` e a configuração de fontes que a GUI precisa
para desenhar as peças. Duas formas de usar:

```bash
# Entrar no ambiente uma vez e trabalhar dentro dele
nix develop        # ou: nix-shell, sem os experimental-features de flakes
cd projeto_final && make stockfish

# Ou rodar um alvo isolado dentro do ambiente
make stockfish USE_NIX=1
```

### Jogar contra Stockfish (com mock do hardware)

```bash
python -m app.main --mode stockfish     # ou: make stockfish
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
  --token TOKEN                Token Lichess (evite: fica visível em `ps`)
  --token-file ARQUIVO         Lê o token de um arquivo
  --lichess-ai {1-8}           Joga contra a IA do Lichess nesse nível
  --lichess-challenge USUARIO  Desafia uma conta específica
  --lichess-game ID            Acompanha uma partida já em andamento
  --lichess-rated              Procura partida ranqueada (padrão: casual)
  --lichess-time MINUTOS       Tempo inicial (padrão: 10)
  --lichess-increment SEGUNDOS Incremento por jogada (padrão: 0)
  --lichess-timeout SEGUNDOS   Espera máxima por um oponente (padrão: 180)
  --flip                       Inverte o tabuleiro
  --no-gui                     Sem interface gráfica
  --log-level LEVEL            Nível de log
```

O tabuleiro é desenhado da perspectiva do jogador físico: com `--color black`
as pretas já ficam embaixo, e `--flip` inverte essa orientação padrão.

### Jogar contra Lichess (online)

#### 1. Token de API

Crie um token em https://lichess.org/account/oauth/token/create com os escopos:

| Escopo | Para quê |
|--------|----------|
| `board:play` | **Obrigatório** — jogar pela Board API |
| `challenge:write` | Só para `--lichess-ai` (criar o desafio) |

#### Onde guardar o token

O token é uma credencial da sua conta: passá-lo em `--token` o deixa no
histórico do shell e visível para qualquer processo via `ps`. Prefira um
arquivo:

```bash
# Na raiz de projeto_final/ — já está no .gitignore
echo 'lip_seu_token' > .lichess_token
chmod 600 .lichess_token

python -m app.main --mode lichess --lichess-ai 3   # acha o token sozinho
```

O arquivo aceita comentários, o que ajuda quando há mais de uma conta:

```
# conta de testes do grupo W
lip_seu_token
```

A busca acontece nesta ordem — a primeira fonte que tiver um token vence:

| Ordem | Fonte |
|-------|-------|
| 1 | `--token TOKEN` |
| 2 | `--token-file ARQUIVO` |
| 3 | `$CHESS_LICHESS_TOKEN` |
| 4 | `$CHESS_LICHESS_TOKEN_FILE` (caminho de um arquivo) |
| 5 | `projeto_final/.lichess_token` |
| 6 | `~/.config/chess-board/lichess_token` |

Um `--token-file` que não puder ser lido é erro, não uma volta silenciosa
para as outras fontes — senão a partida poderia acabar na conta errada. A
aplicação também avisa se o arquivo estiver legível por outros usuários.

> A Board API é para **contas humanas**. Não use uma conta marcada como BOT, e
> não jogue partidas ranqueadas enquanto estiver testando.

#### 2. Jogar

```bash
# Contra a IA do Lichess (não precisa de segundo jogador — melhor para testar)
python -m app.main --mode lichess --lichess-ai 3
# make lichess-ai

# Desafiando uma conta específica (jogar contra alguém combinado)
python -m app.main --mode lichess --lichess-challenge nome_do_usuario
# make lichess-user OPPONENT=nome_do_usuario   (ou: make random-sir)

# Procurando um oponente humano qualquer (partida casual 10+0)
python -m app.main --mode lichess --lichess-time 10 --lichess-increment 0
# make lichess-seek

# Acompanhando uma partida que já está em andamento na conta
python -m app.main --mode lichess --lichess-game AbCdEfGh
# make lichess-game GAME=AbCdEfGh
```

#### Controles de tempo aceitos

A Board API **só aceita rapid ou mais lento**. O Lichess estima a duração de
uma partida em `limite_em_segundos + 40 × incremento` (40 lances) e recusa
qualquer coisa abaixo de **480 s**, respondendo
`{"global":["Invalid time control"]}`. Faz sentido: não dá para operar um
tabuleiro físico em ritmo de blitz.

| Controle | Estimativa | |
|----------|-----------|---|
| `10+0` | 600 s | aceito (padrão da aplicação) |
| `8+0` | 480 s | aceito (limite exato) |
| `5+5` | 500 s | aceito |
| `6+3` | 480 s | aceito |
| `5+3` | 420 s | **recusado** |
| `7+0` | 420 s | **recusado** |
| `3+0` | 180 s | **recusado** |

A aplicação verifica isso antes de conectar e explica o que usar no lugar,
em vez de deixar o 400 do servidor aparecer sem contexto.

Sem nenhuma dessas opções, a aplicação primeiro procura uma partida já em
aberto na conta (dá para começar a partida no site e continuar no tabuleiro
físico) e, se não houver nenhuma, publica um *seek* e espera um oponente até
`--lichess-timeout`.

#### Jogar contra uma segunda conta sua

Duas direções, as duas funcionam:

**Do tabuleiro para o navegador** — a aplicação cria o desafio:

```bash
python -m app.main --mode lichess --lichess-challenge sua_outra_conta
```

O log imprime a URL do desafio; aceite-o logado na outra conta e a partida
começa. Se você fechar a aplicação antes de o desafio ser aceito, ele é
cancelado automaticamente — nada fica pendurado na conta.

**Do navegador para o tabuleiro** — desafie a conta do tabuleiro pelo site
com a aplicação já rodando (`python -m app.main --mode lichess`). Enquanto
espera uma partida, ela **aceita automaticamente** os desafios recebidos e
começa a jogar. Desafios que a própria conta enviou são ignorados.

> Com `--lichess-challenge` dá para escolher a cor (`--color`), o que o seek
> não permite. Use contas diferentes: o Lichess não deixa uma conta desafiar
> a si mesma.

#### 3. Durante a partida

- **A cor quem decide é o Lichess.** `--color` só é respeitado com
  `--lichess-ai`; procurando um humano, o pareamento sorteia a cor (o
  endpoint de seek nem aceita escolha). Se vier a cor oposta, a aplicação se
  reconfigura sozinha — tabuleiro, orientação da GUI e mock — e avisa no log,
  mas o tabuleiro **físico** precisa ser remontado com as peças dessa cor.
- As jogadas do oponente chegam pelo stream e viram instruções físicas: uma
  captura vira "remova a peça de d5".
- Se o Lichess recusar uma jogada, ela não entra no tabuleiro virtual e a
  aplicação pede para desfazê-la no tabuleiro físico.
- Desistência, tempo esgotado e empate são reportados pelo servidor e
  encerram a partida na tela.
- Ofertas de empate e desistência **não** são feitas pelo tabuleiro: use o
  site do Lichess (a oferta recebida aparece no log).

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
| `CHESS_LICHESS_TOKEN_FILE` | Arquivo de onde ler o token | `.lichess_token` |
| `CHESS_LICHESS_API_URL` | URL base da API do Lichess | `https://lichess.org` |
| `CHESS_LICHESS_TIME` | Tempo inicial do seek (min) | `10` |
| `CHESS_LICHESS_INCREMENT` | Incremento do seek (s) | `0` |
| `CHESS_C_PROCESS` | Executável do hardware (ou mock) | `mock/hardware_mock.py` |
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
