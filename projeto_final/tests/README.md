# Testes

Scripts independentes, sem dependências além das do `requirements.txt`.
Nenhum deles precisa de token, de rede, de Stockfish instalado ou de display.

```bash
# Da raiz de projeto_final/
python tests/run_all.py

# Ou uma suíte de cada vez
python tests/test_lichess.py
```

Cada suíte imprime uma linha `PASS`/`FAIL` por cenário e sai com código
diferente de zero se algo falhar.

## O que tem aqui

| Arquivo | O que cobre |
|---------|-------------|
| `fake_lichess.py` | Servidor HTTP que imita a Board API do Lichess. Não é um teste: é a infraestrutura dos outros. |
| `test_lichess.py` | 33 cenários: conta, seek long-polling, streams, controle de tempo, atribuição de cor, sincronização de lances, recusa de jogada, encerramento das threads. |
| `test_challenge.py` | Desafio direto a outra conta, aceite automático de desafio recebido, não-aceite do próprio desafio, cancelamento na saída, usuário inexistente. |
| `test_stockfish_loop.py` | Regressão do loop principal com engine e IPC falsos: partida completa, captura pelo oponente virando instrução física, ressincronização do tabuleiro. |
| `probe_seek.py`, `probe_grid.py` | **Sondas contra o Lichess de verdade** — precisam de token. Veja abaixo. |

## O servidor falso

`fake_lichess.py` implementa os endpoints que a aplicação usa: `/api/account`,
`/api/stream/event` (NDJSON com keep-alive), `/api/board/seek` (long-polling),
`/api/board/game/stream/{id}`, envio de lance, desafios e cancelamento. Ele
responde como o servidor real nos casos que importam — inclusive recusando
token inválido (401) e um seek com campo `color` (400).

Dá para rodá-lo sozinho e apontar a aplicação para ele, o que testa o
programa inteiro sem tocar no Lichess:

```bash
python tests/fake_lichess.py 8777 &

CHESS_LICHESS_API_URL=http://127.0.0.1:8777 \
  python -m app.main --mode lichess --token faketoken123 \
                     --no-gui --ipc stdin --lichess-ai 3
```

Com `--ipc stdin` os eventos de sensor vêm da entrada padrão, então dá para
roteirizar uma partida:

```bash
( sleep 4; echo "e2:0"; sleep 1; echo "e4:1"; sleep 5 ) | \
CHESS_LICHESS_API_URL=http://127.0.0.1:8777 \
  python -m app.main --mode lichess --token faketoken123 \
                     --no-gui --ipc stdin --lichess-ai 3
```

O token aceito pelo servidor falso é `faketoken123`.

## As sondas (`probe_*.py`)

Falam com `https://lichess.org` de verdade e leem o token das fontes normais
da aplicação (`.lichess_token`, `$CHESS_LICHESS_TOKEN`, ...). Foram escritas
para descobrir por que o seek era recusado, e é com elas que a regra de
controle de tempo documentada no README foi verificada.

Cada tentativa fecha a conexão imediatamente — e fechar a conexão **cancela**
o seek, então nada fica publicado na conta. Todas são casuais, nunca
ranqueadas. Ainda assim: são as únicas coisas aqui que tocam a conta real.

```bash
python tests/probe_seek.py    # quais campos o /api/board/seek aceita
python tests/probe_grid.py    # quais combinações (tempo, incremento) passam
```
