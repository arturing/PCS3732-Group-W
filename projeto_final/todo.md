# TODO — Camada Python

Pendências levantadas na revisão de `app/` e `mock/` (2026-07-27), depois da
implementação do modo Lichess. Referências no formato `arquivo.py:linha`.

---

## 1. Testes — cobertura ainda parcial

Já existe suíte em `tests/` (`python tests/run_all.py`, 46 cenários, sem
token/rede/Stockfish/display). Ela cobre o modo Lichess de ponta a ponta e o
loop principal, mas nasceu junto com o modo Lichess — o resto do projeto,
que é anterior, continua sem teste nenhum.

- [ ] Cobrir o que hoje não tem teste e não depende de hardware nem de GUI:
  - `parse_event` (`ipc_reader.py`) — linhas malformadas, casas inválidas
  - `MoveInterpreter` — roque num evento só, promoção, en passant
  - `build_board_instruction` / `build_undo_instruction`
  - **a máquina de estados de peças deslocadas e do roque em duas etapas**
    (`ChessApplication`) — a parte mais sutil do projeto, hoje exercitada só
    de raspão pelos testes do modo Lichess
- [ ] Converter os `check(...)` caseiros para `pytest` (opcional; daria
      integração com CI de graça, ao custo de uma dependência nova)

---

## 2. Funcionalidades documentadas que não existem

### 2.1 Promoção: o diálogo é código morto
`gui.py:547` define `show_promotion_dialog()`, mas **nada o chama**.
`move_interpreter.py:151` promove sempre para dama, em silêncio. O README
ainda lista `Q/R/B/N` como atalho funcional na tabela de teclas.

- [ ] Ligar o diálogo em `_try_apply_move`, **ou** remover o método e a linha
      do README, documentando a promoção automática para dama

### 2.2 `send_to_process()` nunca envia nada
`ipc_reader.py:226` só escreve se `self._process.stdin` existir, mas
`_start_subprocess` define `stdin=None` nas duas plataformas
(`ipc_reader.py:154` e `:159`). O `main.py:819` manda `opp <lance>` a cada
jogada do Stockfish e isso cai no vazio — e o `hardware_mock` nem tem um
comando `opp` para receber.

- [ ] Decidir: apagar os dois lados, **ou** abrir `stdin=subprocess.PIPE` e
      implementar o comando no mock. Atenção: no modo GUI o mock não lê
      stdin, então só o modo interativo se beneficiaria.

### 2.3 `show_message()` está quebrado
`gui.py:514` escreve em `self._last_message`, que é o *cache de comparação*
do desenho incremental. Resultado: não desenha nada e ainda suprime o próximo
desenho legítimo daquela mensagem. `_message_color` (`gui.py:153`, `:522`) é
escrito e nunca lido. O método não é usado por ninguém.

- [ ] Apagar `show_message()` e `_message_color`

---

## 3. Limitações conhecidas do modo Lichess

- [ ] **Limite de controle de tempo verificado só no seek.** A regra
      `limite + 40 × incremento ≥ 480 s` foi confirmada empiricamente contra
      `/api/board/seek` (15 combinações). Para `--lichess-ai` e
      `--lichess-challenge` a aplicação apenas **avisa**, porque o endpoint de
      desafio não foi testado com controle de tempo rápido. Confirmar e, se
      valer o mesmo, transformar o aviso em erro (`main.py:_check_time_control`).
- [ ] **`send_move()` bloqueia o loop principal.** É um POST síncrono com
      timeout de 15 s dentro de `_commit_move`; na prática leva ~100 ms, mas
      numa rede ruim a GUI congela. Mover para uma thread com fila de saída.
- [ ] **Não dá para oferecer/aceitar empate nem desistir pelo tabuleiro.**
      A oferta recebida só aparece no log (`_note_draw_offer`); responder
      exige o site. O cliente já tem `resign()`, falta expor.
- [ ] **Falso positivo na validação de tempo.** `_check_time_control` roda
      antes de saber se existe partida em aberto: rodar com
      `--lichess-time 5 --lichess-increment 3` impede até de *retomar* uma
      partida rapid já em andamento. Só validar quando o seek for mesmo usado.
- [ ] **Takeback deixa o estado divergente.** `_sync_moves_from_lichess`
      detecta que o servidor tem menos lances que o local, avisa e desiste.
      Deveria reconstruir o tabuleiro a partir da lista do servidor.

---

## 4. Limpezas

- [ ] `gui.py:317` — `is_light` está com o nome invertido: a1 (file 0, rank 0)
      dá `is_light=True` e recebe `DARK_SQUARE_COLOR`. O desenho está certo,
      só o nome engana. Renomear para `is_dark`.
- [ ] `move_interpreter.py:41,45,47` — `accumulate()`, `reset()` e
      `_pending_changes` não são usados; quem acumula estado é o
      `physical_board_state` do `main.py`. Apagar.
- [ ] `config.py:196` — `INITIAL_FEN` não é usado (o python-chess já começa
      nessa posição). Apagar.
- [ ] `game_state.py` — `get_last_move_san()`, `get_full_move_list()`,
      `get_move_san()` e `undo_last_move()` não são chamados por ninguém.
      `undo_last_move()` ainda por cima não restaura `_message`, então
      deixaria um "Xeque-mate!" velho na tela se fosse usado. Apagar ou usar.
- [ ] `stockfish_engine.py:111` + `main.py:815` — o mesmo lance é logado duas
      vezes por turno.
- [ ] `hardware_mock.py:470` — restaurar `SIGPIPE` para `SIG_DFL` mata o mock
      na hora em que a aplicação fecha o pipe, o que anula o encerramento
      limpo do `gui_mock.py:_emit` (que captura `OSError` justamente para
      fechar a janela direito). Remover e deixar o `BrokenPipeError` subir.
- [ ] `ipc_reader.py:63,68` — um par malformado descarta o evento inteiro. Com
      uma matriz que manda vários pares por linha, é melhor pular o par ruim
      e aproveitar o resto.

---

## 5. Ideias

- [ ] Aceitar desafios recebidos também **durante** a partida (hoje só na
      janela de espera inicial)
- [ ] Reconectar sozinho se o stream da partida cair no meio do jogo
- [ ] Mostrar os relógios do Lichess (`wtime`/`btime` já chegam no
      `gameState` e são ignorados)
- [ ] Suportar variantes (hoje só xadrez padrão)
