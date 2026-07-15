# Experimento 7 - Metrônomo
## Diagrama de Blocos
```mermaid
flowchart TD
    %% Nós principais
    Start([Início do Programa]) --> Init[Definir Pinos e Variáveis Iniciais<br>BPM = 60]
    Init --> Setup[setup_hardware<br>Configurar GPIOs, PWM, Callbacks]
    Setup --> StartLoop[Iniciar metronome_loop]
    
    %% Loop Principal
    subgraph "Loop Principal (Metrônomo)"
        StartLoop --> Loop{while True}
        
        Loop --> |Executa| Tick[Salvar start_time]
        Tick --> AtivaOutput[Ligar Buzzer e LED a 100%]
        CheckServo{servo_pos é True?}
        AtivaOutput --> CheckServo
        
        CheckServo -->|Sim| Servo10[Servo Duty = 10.0%]
        CheckServo -->|Não| Servo5[Servo Duty = 5.0%]
        
        Servo10 --> ToggleServo[Inverter servo_pos]
        Servo5 --> ToggleServo
        
        ToggleServo --> Wait50[Aguardar 50ms]
        Wait50 --> DesativaOutput[Desligar Buzzer e LED a 0%]
        DesativaOutput --> CalcTime[Calcular tempo restante do compasso<br>sleep_delta]
        
        CalcTime --> CheckDelta{sleep_delta > 0?}
        CheckDelta -->|Sim| WaitDelta[Aguardar sleep_delta]
        CheckDelta -->|Não| Loop
        WaitDelta --> Loop
    end

    %% Eventos de Interrupção (Assíncronos)
    subgraph "Eventos Assíncronos (Callbacks)"
        direction TB
        BtnUp((Botão UP<br>Pino 20)) -.-> |FALLING_EDGE| CallbackUp[increase_bpm:<br>BPM += 5<br>Recalcular beat_interval]
        BtnDown((Botão DOWN<br>Pino 21)) -.-> |FALLING_EDGE| CallbackDown[decrease_bpm:<br>BPM -= 5<br>Recalcular beat_interval]
    end

    %% Encerramento
    Loop -.-> |KeyboardInterrupt<br>CTRL+C| Limpeza[Bloco finally:<br>Desligar LED, Servo e Buzzer<br>Fechar gpiochip_close]
    Limpeza --> Fim([Fim do Programa])

    %% Estilos visuais
    classDef main fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef async fill:#fff3e0,stroke:#e65100,stroke-width:2px,stroke-dasharray: 5 5;
    classDef io fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px;
    
    class Loop,Tick,AtivaOutput,DesativaOutput,Wait50,CalcTime main;
    class CallbackUp,CallbackDown async;
    class Limpeza io;
```

## Diagrama de Sequência
```mermaid
sequenceDiagram
    actor Usuario as Usuário
    participant Main as Script (__main__)
    participant Setup as setup_hardware()
    participant MLoop as metronome_loop()
    participant Callback as Callbacks de BPM
    participant LGPIO as lgpio (Biblioteca)
    participant HW as Hardware Físico

    Usuario->>Main: Executa o código
    Main->>Setup: setup_hardware()
    Setup->>LGPIO: gpiochip_open(0)
    Setup->>LGPIO: Configura pinos (PWM e Saídas)
    Setup->>LGPIO: Configura Botões (Debounce e Alertas)
    Setup->>LGPIO: Registra callbacks (FALLING_EDGE)
    LGPIO-->>Setup: Pinos reservados
    Setup-->>Main: Configuração concluída

    Main->>MLoop: metronome_loop()
    
    rect rgb(240, 248, 255)
        loop Laço Infinito (while True)
            MLoop->>MLoop: Marca start_time
            MLoop->>LGPIO: Ativa Buzzer e tx_pwm(LED, 100%)
            
            alt servo_pos == True
                MLoop->>LGPIO: tx_pwm(Servo, 10%)
            else servo_pos == False
                MLoop->>LGPIO: tx_pwm(Servo, 5%)
            end
            
            LGPIO->>HW: Ativa componentes
            MLoop->>MLoop: Inverte servo_pos
            MLoop->>MLoop: time.sleep(0.05)
            
            MLoop->>LGPIO: Desativa Buzzer e tx_pwm(LED, 0%)
            LGPIO->>HW: Desativa som e luz
            
            MLoop->>MLoop: Calcula sleep_delta (beat_interval - drift_time)
            MLoop->>MLoop: time.sleep(sleep_delta)
        end
    end

    %% Eventos Assíncronos sobrepostos ao funcionamento
    rect rgb(255, 245, 230)
        note over Usuario, HW: "Eventos Assíncronos (Podem ocorrer a qualquer momento)"
        Usuario->>HW: Pressiona Botão UP ou DOWN
        HW->>LGPIO: Sinal de Interrupção (Borda de Descida)
        LGPIO->>Callback: Dispara increase_bpm() ou decrease_bpm()
        Callback->>Callback: Atualiza variáveis globais (bpm, beat_interval)
    end

    %% Tratamento do encerramento
    rect rgb(255, 235, 235)
        Usuario->>MLoop: Pressiona CTRL+C (KeyboardInterrupt)
        MLoop->>MLoop: Interrompe o Laço Infinito (try/except)
        MLoop->>LGPIO: Bloco finally: Desliga LED, Servo e Buzzer
        LGPIO->>HW: Hardware zerado
        MLoop->>LGPIO: gpiochip_close()
        MLoop-->>Main: Retorna
        Main-->>Usuario: Programa encerrado
    end
```
