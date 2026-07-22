# Experimento 8 - Fechadura Eletrônica

## Visão Geral
Esta é a implementação de uma **Fechadura Eletrônica** baseada no Raspberry Pi 3. A Unidade de Controle Central atua como Mestre e gerencia quatro periféricos principais:
1. **Teclado Matricial 4x4**: Entrada de senhas.
2. **Display LCD 16x2 (I2C)**: Feedback visual em tempo real.
3. **Sensor Ultrassônico HC-SR04**: Monitoramento da integridade da tranca física.
4. **Buzzer**: Feedback sonoro (sucesso, falha e alarmes).

A arquitetura de software é baseada em um fluxo não-bloqueante (máquina de estados), garantindo que o Raspberry Pi não congele a varredura do teclado ou do sensor durante a exibição de mensagens.

## Diagrama de Blocos

```mermaid
graph TD
    subgraph Entradas [Sensores e Entradas]
        KEYPAD["Teclado Matricial 4x4<br/>Pinos GPIO (Linhas e Colunas)"]
        SENSOR["Sensor Ultrassônico HC-SR04<br/>Pinos TRIG e ECHO"]
    end

    subgraph Processamento [Controle Central RPi3]
        SM["Máquina de Estados<br/>(IDLE, INPUT, PROCESSING, SUCCESS, FAILURE, COOLDOWN, ALARM)"]
        HASH["Hash SHA-256<br/>Comparação de Senhas"]
        DEBOUNCE["Filtro Anti-Bouncing<br/>Teclado"]
    end

    subgraph Saidas [Atuadores e Feedback]
        LCD["Display LCD 16x2<br/>Barramento I2C (SDA/SCL)"]
        BUZZER["Buzzer Passivo<br/>Pino Digital GPIO"]
    end

    KEYPAD -->|"Polling + Debounce"| DEBOUNCE
    DEBOUNCE -->|"Dígito Válido"| SM
    SENSOR -->|"Polling de Distância"| SM
    
    SM <-->|"Valida Credencial"| HASH
    
    SM -->|"Mensagens de Status"| LCD
    SM -->|"Bipes Curtos/Longos/Alarme"| BUZZER
```

## Diagrama de Sequência

```mermaid
sequenceDiagram
    actor Usuario as Usuário
    participant Keypad as Teclado Matricial
    participant SM as Máquina de Estados
    participant Sensor as HC-SR04
    participant Buzzer as Buzzer
    participant LCD as Display LCD I2C

    %% Fluxo Normal - Acesso Autorizado
    Usuario->>Keypad: Digita Senha + '#'
    Keypad->>SM: Envia caracteres (debounce aplicado)
    SM->>LCD: Atualiza asteriscos (*)
    SM->>SM: Calcula Hash SHA-256
    SM->>SM: Compara com Hash Salvo
    
    alt Senha Correta
        SM->>LCD: Exibe ">>> Aberto <<<"
        SM->>Buzzer: Emite Bipe Curto (Sucesso)
        SM->>SM: Estado SUCCESS
        Note over SM: Abre a tranca (Lógica)
    else Senha Incorreta
        SM->>LCD: Exibe "Acesso Negado!"
        SM->>Buzzer: Emite Bipe Longo (Falha)
        SM->>SM: Incrementa falhas (Estado FAILURE)
    end
    
    %% Alarme Físico
    rect rgb(255, 235, 235)
        Note over Sensor, SM: Evento Assíncrono (Sensor Polling)
        Sensor->>SM: Distância > 10cm (Porta Aberta)
        SM->>SM: Verifica se estado esperado é "Trancada"
        SM->>LCD: Exibe "!!! ALARME !!!"
        SM->>Buzzer: Emite Bipes Intermitentes
        SM->>SM: Estado ALARM
    end
```

## Fluxograma da Máquina de Estados (SM)

Este diagrama detalha o algoritmo principal baseado em uma máquina de estados finitos, com ênfase na recuperação de erros e bloqueio de tentativas (RNF1).

```mermaid
flowchart TD
    %% Estilos opcionais para destacar estados críticos
    classDef state fill:#f9f9f9,stroke:#333,stroke-width:2px;
    classDef cooldown fill:#ffebee,stroke:#f44336,stroke-width:3px;
    classDef alarm fill:#fff3e0,stroke:#ff9800,stroke-width:3px;

    Start([Início]) --> IDLE
    
    %% Estados principais
    IDLE((IDLE)):::state --> |"Tecla Pressionada\n(1-9)"| INPUT((INPUT)):::state
    INPUT --> |"Tecla '*'\n(Apagar, se vazio)"| IDLE
    
    INPUT --> |"Tecla '#'\n(Confirmar)"| PROCESSING((PROCESSING)):::state
    
    %% Validação
    PROCESSING --> |"Hash Válido"| SUCCESS((SUCCESS)):::state
    PROCESSING --> |"Hash Inválido"| FAILURE((FAILURE)):::state
    
    %% Sucesso
    SUCCESS --> |"Timeout de Exibição\n(Acesso Liberado)"| IDLE
    
    %% Falha (RNF1 destacado)
    FAILURE --> |"Incrementa Falhas++"| CheckFailures{"Falhas >= 3?"}
    
    CheckFailures --> |"Não"| IDLE
    CheckFailures --> |"Sim"| COOLDOWN((COOLDOWN)):::cooldown
    
    %% RNF1: Bloqueio de 30s
    COOLDOWN --> |"Espera 30s\n(Zera Falhas = 0)"| IDLE
    
    %% Alarme (RF3) - Pode ocorrer de quase qualquer estado
    MonitorSensor["Monitoramento Contínuo\n(Sensor Ultrassônico)"] -.-> |"Distância > Limiar\ne\nPorta Trancada"| ALARM((ALARM)):::alarm
    
    ALARM --> |"Porta fechada novamente"| IDLE
```

## Matriz de Validação: Requisitos e Testes

| Requisito | Teste Executado | Resultado Esperado (Telemetria) |
|---|---|---|
| **RF1:** O sistema deve registrar senhas numéricas via teclado. | Inserção de sequência limite (4 a 6 dígitos), incluindo botão de *backspace* (*). | Captura exata e precisa sem ocorrência de *bouncing* de teclas. |
| **RF2:** O LCD deve exibir o status em tempo real. | Transição de estado de bloqueado para desbloqueado. | Atualização da tela concluída em menos de 200ms após a validação. |
| **RF3:** O sensor deve verificar a integridade física da tranca. | Simulação de porta aberta com a fechadura no estado "Trancada". | Disparo automático de alerta sonoro no Buzzer e visual no LCD (Alarme). |
| **RNF1:** Recuperação de erros de entrada (Confiabilidade). | Submissão de múltiplas entradas de senha incorretas (3) consecutivas. | Bloqueio temporário (*cooldown* de 30s) sem que ocorra travamento do SO. |

## Segurança e Ameaças

1. **Spoofing de Sensor:** Um atacante pode tentar colocar um objeto na frente do sensor ultrassônico para fingir que a porta está fechada enquanto a arromba. Embora seja uma ameaça física válida, a montagem embutida do sensor no batente da porta mitiga essa abordagem.
2. **Timing Attacks:** O uso de Raspberry Pi com Linux (agendador multitarefa) cria pequenas variações de tempo no processamento. O sistema armazena a senha usando Hash SHA-256 via a biblioteca `hashlib`, mitigando armazenamento em texto plano.
3. **Ghosting/Bouncing:** Tratado inteiramente em software com um delay programático não-bloqueante (`KEY_DEBOUNCE_TIME = 0.05s`), assegurando que apenas uma tecla é registrada por pressionamento.

## Gerenciamento de Senha

Para alterar a senha da fechadura (armazenada de forma segura utilizando hash SHA-256), é fornecido um script bash auxiliar. Ele calcula o hash da nova senha e atualiza automaticamente o arquivo `fechadura.py`.

**Uso:**
```bash
./change_password.sh <nova_senha>
```
