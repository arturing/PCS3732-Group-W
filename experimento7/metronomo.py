import lgpio
import time

# ==========================================
# Configuração e Mapeamento de Pinos (BCM)
# ==========================================
PIN_LED = 17
PIN_SERVO = 18
PIN_BUZZER = 12
PIN_BTN_UP = 20
PIN_BTN_DOWN = 21

# ==========================================
# Variáveis Globais de Estado
# ==========================================
bpm = 60
beat_interval = 60.0 / bpm
servo_pos = False  # Alterna o estado do braço mecânico
h = None           # Handle do chip GPIO

# ==========================================
# Rotinas de Interrupção (Callbacks)
# ==========================================
# No lgpio, a assinatura do callback exige (chip, gpio, level, timestamp)
def increase_bpm(chip, gpio, level, timestamp):
    global bpm, beat_interval
    bpm += 5
    beat_interval = 60.0 / bpm
    print(f"Interrupção: BPM aumentado para {bpm}")

def decrease_bpm(chip, gpio, level, timestamp):
    global bpm, beat_interval
    bpm = max(10, bpm - 5)  # Impede que o BPM seja negativo ou nulo
    beat_interval = 60.0 / bpm
    print(f"Interrupção: BPM diminuído para {bpm}")

# ==========================================
# Inicialização de Hardware
# ==========================================
def setup_hardware():
    global h
    
    # Abre o chip GPIO principal (geralmente chip 0 na Raspberry Pi)
    h = lgpio.gpiochip_open(0)

    # 1. Configuração do LED (PWM a 1kHz)
    # lgpio.tx_pwm(handle, pino, frequência_hz, duty_cycle_porcentagem)
    lgpio.tx_pwm(h, PIN_LED, 1000, 0.0)

    # 2. Configuração do Servomotor SG90 (PWM a 50Hz)
    lgpio.tx_pwm(h, PIN_SERVO, 50, 0.0)

    # 3. Configuração do Buzzer (Sinal Digital)
    # Reivindica o pino como saída e inicia em LOW (0)
    lgpio.gpio_claim_output(h, PIN_BUZZER, level=0)

    # 4. Configuração dos Botões
    # Reivindica os pinos para alertas na borda de descida (FALL_EDGE) com Pull-Up ativado
    lgpio.gpio_claim_alert(h, PIN_BTN_UP, lgpio.FALLING_EDGE, lgpio.SET_PULL_UP)
    lgpio.gpio_claim_alert(h, PIN_BTN_DOWN, lgpio.FALLING_EDGE, lgpio.SET_PULL_UP)

    # Filtro de bouncing (debounce é setado em microssegundos: 200ms = 200.000 µs)
    lgpio.gpio_set_debounce_micros(h, PIN_BTN_UP, 200000)
    lgpio.gpio_set_debounce_micros(h, PIN_BTN_DOWN, 200000)

    # Registro das funções de interrupção
    lgpio.callback(h, PIN_BTN_UP, lgpio.FALLING_EDGE, increase_bpm)
    lgpio.callback(h, PIN_BTN_DOWN, lgpio.FALLING_EDGE, decrease_bpm)

# ==========================================
# Thread Principal (Loop Metrônomo)
# ==========================================
def metronome_loop():
    global servo_pos
    print(f"Metrônomo iniciado a {bpm} BPM. Pressione CTRL+C para sair.")
    
    try:
        while True:
            # Captura a timestamp exata no início do loop
            start_time = time.time()

            # --- ATUAÇÃO DOS PERIFÉRICOS ---
            # Aciona o buzzer (HIGH = 1)
            lgpio.gpio_write(h, PIN_BUZZER, 1)
            
            # Aciona o LED (Duty Cycle máximo = 100.0)
            lgpio.tx_pwm(h, PIN_LED, 1000, 100.0)
            
            # Alterna posição do Servomotor (5% DC = ~1.0ms, 10% DC = ~2.0ms)
            if servo_pos:
                lgpio.tx_pwm(h, PIN_SERVO, 50, 10.0) 
            else:
                lgpio.tx_pwm(h, PIN_SERVO, 50, 5.0)
            servo_pos = not servo_pos

            # Mantém os atuadores ativos pelo pulso mecânico/sônico (~50ms de atividade)
            time.sleep(0.05)
            
            # Desliga buzzer e LED (Servo mantém a posição fisicamente)
            lgpio.gpio_write(h, PIN_BUZZER, 0)
            lgpio.tx_pwm(h, PIN_LED, 1000, 0.0)

            # --- CÁLCULO DE DRIFT E ESPERA ATIVA ---
            # Calcula quanto tempo o laço atual levou executando as lógicas e atuadores
            drift_time = time.time() - start_time
            sleep_delta = beat_interval - drift_time

            # Se o processamento tomou menos tempo que o intervalo, dormimos a diferença
            if sleep_delta > 0:
                time.sleep(sleep_delta)

    except KeyboardInterrupt:
        print("\nSinal de interrupção recebido. Limpando GPIOs...")
    finally:
        # Encerramento seguro
        if h is not None:
            # Zera as saídas ativas antes de fechar o chip
            lgpio.tx_pwm(h, PIN_LED, 1000, 0.0)
            lgpio.tx_pwm(h, PIN_SERVO, 50, 0.0)
            lgpio.gpio_write(h, PIN_BUZZER, 0)
            # Fecha a comunicação com o chip GPIO
            lgpio.gpiochip_close(h)

if __name__ == '__main__':
    setup_hardware()
    metronome_loop()