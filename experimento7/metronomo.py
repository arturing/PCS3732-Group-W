import lgpio
import time
import math

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
    lgpio.gpio_claim_output(h, PIN_LED, level=0)
    lgpio.tx_pwm(h, PIN_LED, 100, 0.0)

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
            # Marca o início exato da batida atual
            start_time = time.time()
 
            # --- O "TICK" (Início do compasso) ---
            lgpio.gpio_write(h, PIN_BUZZER, 1)
            buzzer_active = True

            if servo_pos:
                lgpio.tx_pwm(h, PIN_SERVO, 50, 10.0)
            else:
                lgpio.tx_pwm(h, PIN_SERVO, 50, 5.0)
 
            # --- CICLO DE ANIMAÇÃO DINÂMICA ---
            # Este laço roda continuamente durante o tempo de 1 batida (beat_interval)
            while True:
                current_time = time.time()
                elapsed = current_time - start_time
 
                # Verifica se já completou o tempo da batida para ir para a próxima
                if elapsed >= beat_interval:
                    break
 
                # O Buzzer só precisa de 50ms (0.05s) para gerar um som seco e nítido
                if buzzer_active and elapsed >= 0.05:
                    lgpio.gpio_write(h, PIN_BUZZER, 0)
                    buzzer_active = False
 
                # Calcula o progresso atual do tempo entre 0.0 (início) e 1.0 (fim da batida)
                progress = elapsed / beat_interval
 
                # 1. LED Fading (Decaimento Linear)
                # Começa em 100% e cai proporcionalmente até 0% no fim do intervalo
                led_dc = ((1.0 - progress) ** 3)* 100.0
                led_dc = max(0.0, min(100.0, led_dc))
                lgpio.tx_pwm(h, PIN_LED, 100, round(led_dc, 1))
 
                                # Pequeno repouso de 10ms para o Raspberry Pi não gargalar a CPU a 100%
                time.sleep(0.02)
 
            # Inverte o estado mecânico do pêndulo para a próxima batida
            servo_pos = not servo_pos
 
    except KeyboardInterrupt:
        print("\nSinal de interrupção recebido. Limpando GPIOs...")
    finally:
        if h is not None:
            # Zera saídas para segurança
            lgpio.tx_pwm(h, PIN_LED, 100, 0.0)
            lgpio.tx_pwm(h, PIN_SERVO, 50, 0.0)
            lgpio.gpio_write(h, PIN_BUZZER, 0)
            lgpio.gpiochip_close(h)

if __name__ == '__main__':
    setup_hardware()
    metronome_loop()