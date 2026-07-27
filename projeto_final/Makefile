# Makefile — atalhos para os modos de execução do projeto_final.
#
#   make                  lista os alvos disponíveis
#   make stockfish        joga contra o Stockfish local
#   make lichess-ai       joga contra a IA do Lichess
#   make random-sir       desafia a conta "random-sir" no Lichess
#   make lichess-user OPPONENT=fulano    desafia a conta informada
#
# Todo alvo aceita variáveis na linha de comando (COLOR, LICHESS_LEVEL, ...)
# e um ARGS livre repassado ao `app.main`:
#
#   make stockfish COLOR=black STOCKFISH_TIME=2.0
#   make lichess-ai LICHESS_LEVEL=6 ARGS="--log-level DEBUG"

# ---------------------------------------------------------------------------
#  Variáveis configuráveis
# ---------------------------------------------------------------------------

# Atenção ao editar: em Make, um comentário no fim da linha de atribuição
# entraria no valor da variável (com os espaços antes dele) — daí cada
# comentário ficar em linha própria.
PYTHON          ?= python3

# Cor das peças físicas: white|black
COLOR           ?= white
# Nível de log: DEBUG|INFO|WARNING|ERROR
LOG_LEVEL       ?= INFO
# Opções extras repassadas ao app.main
ARGS            ?=

# Segundos de cálculo por lance
STOCKFISH_TIME  ?= 1.0
# Vazio = usa $CHESS_STOCKFISH_PATH ou o stockfish do PATH
STOCKFISH_PATH  ?=

# Nível da IA do Lichess (1-8)
LICHESS_LEVEL   ?= 3
# Minutos iniciais (a Board API exige o equivalente a 8+0 ou mais lento)
LICHESS_TIME    ?= 10
# Incremento por lance, em segundos
LICHESS_INC     ?= 0
# Espera máxima por um oponente, em segundos
LICHESS_TIMEOUT ?= 180
# Conta a desafiar em `make lichess-user`
OPPONENT        ?=
# Id de partida em `make lichess-game`
GAME            ?=

# Conta usada por `make random-sir`.
RANDOM_SIR      := random-sir

# Mock do hardware executado standalone (`make mock`): gui|interactive|auto|scripted
MOCK_MODE       ?= gui
MOCK_ARGS       ?=

# USE_NIX=1 roda cada alvo dentro do devShell do flake (traz python com as
# dependências, o Stockfish e a config de fontes). Sem isso, assume-se que o
# ambiente atual já tem tudo — inclusive quando já se está dentro do shell.
ifeq ($(USE_NIX),1)
RUN := nix develop $(CURDIR)/.. --command
else
RUN :=
endif

# `python -m app.main` precisa rodar com projeto_final/ como diretório atual;
# `make -C projeto_final` e `make` de dentro dele já garantem isso.
APP  = $(RUN) $(PYTHON) -m app.main --color $(COLOR) --log-level $(LOG_LEVEL)

STOCKFISH_OPTS = --mode stockfish --stockfish-time $(STOCKFISH_TIME) \
                 $(if $(STOCKFISH_PATH),--stockfish-path $(STOCKFISH_PATH))

LICHESS_OPTS   = --mode lichess --lichess-time $(LICHESS_TIME) \
                 --lichess-increment $(LICHESS_INC) \
                 --lichess-timeout $(LICHESS_TIMEOUT)

.PHONY: help stockfish lichess-ai random-sir lichess-user lichess-seek \
        lichess-game mock test deps shell shell-classic check-token clean

# ---------------------------------------------------------------------------
#  Ajuda (alvo padrão)
# ---------------------------------------------------------------------------

help:
	@echo 'Tabuleiro de Xadrez Eletrônico — alvos disponíveis:'
	@echo ''
	@echo '  make stockfish                     joga contra o Stockfish local'
	@echo '  make lichess-ai                    joga contra a IA do Lichess (nível $(LICHESS_LEVEL))'
	@echo '  make random-sir                    desafia a conta "$(RANDOM_SIR)" no Lichess'
	@echo '  make lichess-user OPPONENT=fulano  desafia a conta informada'
	@echo '  make lichess-seek                  procura um oponente humano qualquer'
	@echo '  make lichess-game GAME=AbCdEfGh    retoma uma partida já em andamento'
	@echo ''
	@echo '  make mock                          roda só o mock do hardware'
	@echo '  make test                          roda a suíte de testes'
	@echo '  make deps                          instala as dependências Python'
	@echo '  make shell                         abre o devShell do Nix (nix-shell: make shell-classic)'
	@echo '  make clean                         remove __pycache__ e caches'
	@echo ''
	@echo 'Variáveis (make <alvo> VAR=valor):'
	@echo '  COLOR=$(COLOR)  LOG_LEVEL=$(LOG_LEVEL)  ARGS=...'
	@echo '  STOCKFISH_TIME=$(STOCKFISH_TIME)  STOCKFISH_PATH=$(STOCKFISH_PATH)'
	@echo '  LICHESS_LEVEL=$(LICHESS_LEVEL)  LICHESS_TIME=$(LICHESS_TIME)  LICHESS_INC=$(LICHESS_INC)  LICHESS_TIMEOUT=$(LICHESS_TIMEOUT)'
	@echo '  USE_NIX=1                          roda o alvo dentro do devShell do flake'

# ---------------------------------------------------------------------------
#  Modos de jogo
# ---------------------------------------------------------------------------

# Partida offline contra o Stockfish. Não precisa de rede nem de token.
stockfish:
	$(APP) $(STOCKFISH_OPTS) $(ARGS)

# Partida contra a IA do Lichess: não depende de um segundo jogador, é o
# caminho mais rápido para testar o modo online de ponta a ponta.
lichess-ai: check-token
	$(APP) $(LICHESS_OPTS) --lichess-ai $(LICHESS_LEVEL) $(ARGS)

# Desafio direto à conta random-sir. A URL do desafio sai no log; ele precisa
# ser aceito do outro lado (e é cancelado se a aplicação for fechada antes).
random-sir:
	@$(MAKE) --no-print-directory lichess-user OPPONENT=$(RANDOM_SIR)

# Desafio direto a uma conta qualquer. O Lichess não deixa uma conta desafiar
# a si mesma: OPPONENT tem de ser diferente da conta do token.
lichess-user: check-token
	@test -n "$(OPPONENT)" || { \
	  echo 'Erro: informe a conta a desafiar — make lichess-user OPPONENT=fulano'; \
	  exit 2; }
	$(APP) $(LICHESS_OPTS) --lichess-challenge $(OPPONENT) $(ARGS)

# Seek aberto: o Lichess pareia com um humano qualquer e sorteia a cor
# (COLOR é ignorado aqui — o endpoint de seek não aceita escolha).
lichess-seek: check-token
	$(APP) $(LICHESS_OPTS) $(ARGS)

# Retoma no tabuleiro físico uma partida já em andamento na conta.
lichess-game: check-token
	@test -n "$(GAME)" || { \
	  echo 'Erro: informe o id da partida — make lichess-game GAME=AbCdEfGh'; \
	  exit 2; }
	$(APP) --mode lichess --lichess-game $(GAME) $(ARGS)

# ---------------------------------------------------------------------------
#  Apoio
# ---------------------------------------------------------------------------

# Falha antes de abrir a janela quando não há token: o erro do servidor
# (401) não diz que a credencial simplesmente não foi encontrada.
check-token:
	@$(RUN) $(PYTHON) -c 'from app.config import LICHESS_TOKEN; raise SystemExit(0 if LICHESS_TOKEN else 1)' || { \
	  echo 'Erro: token do Lichess não encontrado.'; \
	  echo 'Crie um em https://lichess.org/account/oauth/token/create com os escopos'; \
	  echo 'board:play e challenge:write, e salve-o em projeto_final/.lichess_token:'; \
	  echo "  echo 'lip_seu_token' > .lichess_token && chmod 600 .lichess_token"; \
	  exit 2; }

mock:
	$(RUN) $(PYTHON) -m mock.hardware_mock --mode $(MOCK_MODE) --color $(COLOR) $(MOCK_ARGS)

test:
	$(RUN) $(PYTHON) tests/run_all.py

deps:
	$(RUN) $(PYTHON) -m pip install -r requirements.txt

shell:
	nix develop $(CURDIR)/..

# Mesmo ambiente para quem não tem os experimental-features de flakes.
shell-classic:
	nix-shell $(CURDIR)/..

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache

.DEFAULT_GOAL := help
