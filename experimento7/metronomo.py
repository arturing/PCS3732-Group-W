import lgpio
import time
import math

PIN_LED = 17
PIN_SERVO = 18
PIN_BUZZER = 12
PIN_BTN_UP = 20
PIN_BTN_DOWN = 21

bpm = 60
beat_interval = 60.0 / bpm
servo_pos = False  
h = None           

def increase_bpm(chip, gpio, level, timestamp):
    global bpm, beat_interval
    bpm += 5
    beat_interval = 60.0 / bpm
    print(f"Interrupção: BPM aumentado para {bpm}")

def decrease_bpm(chip, gpio, level, timestamp):
    global bpm, beat_interval
    bpm = max(10, bpm - 5) 
    beat_interval = 60.0 / bpm
    print(f"Interrupção: BPM diminuído para {bpm}")

def setup_hardware():
    global h
    
    h = lgpio.gpiochip_open(0)

    lgpio.gpio_claim_output(h, PIN_LED, level=0)
    lgpio.tx_pwm(h, PIN_LED, 100, 0.0)

    lgpio.tx_pwm(h, PIN_SERVO, 50, 0.0)
    lgpio.gpio_claim_output(h, PIN_BUZZER, level=0)

    lgpio.gpio_claim_alert(h, PIN_BTN_UP, lgpio.FALLING_EDGE, lgpio.SET_PULL_UP)
    lgpio.gpio_claim_alert(h, PIN_BTN_DOWN, lgpio.FALLING_EDGE, lgpio.SET_PULL_UP)

    lgpio.gpio_set_debounce_micros(h, PIN_BTN_UP, 200000)
    lgpio.gpio_set_debounce_micros(h, PIN_BTN_DOWN, 200000)

    lgpio.callback(h, PIN_BTN_UP, lgpio.FALLING_EDGE, increase_bpm)
    lgpio.callback(h, PIN_BTN_DOWN, lgpio.FALLING_EDGE, decrease_bpm)

def metronome_loop():
    global servo_pos
    print(f"Metrônomo iniciado a {bpm} BPM. Pressione CTRL+C para sair.")
 
    try:
        while True:
            start_time = time.time()
 
            lgpio.gpio_write(h, PIN_BUZZER, 1)
            buzzer_active = True

            if servo_pos:
                lgpio.tx_pwm(h, PIN_SERVO, 50, 10.0)
            else:
                lgpio.tx_pwm(h, PIN_SERVO, 50, 5.0)
 
            while True:
                current_time = time.time()
                elapsed = current_time - start_time
                if elapsed >= beat_interval:
                    break
                if buzzer_active and elapsed >= 0.05:
                    lgpio.gpio_write(h, PIN_BUZZER, 0)
                    buzzer_active = False

                progress = elapsed / beat_interval
 
                led_dc = ((1.0 - progress) ** 3)* 100.0
                led_dc = max(0.0, min(100.0, led_dc))
                lgpio.tx_pwm(h, PIN_LED, 100, round(led_dc, 1))
 
                time.sleep(0.02)

            servo_pos = not servo_pos
 
    except KeyboardInterrupt:
        print("\nSinal de interrupção recebido. Limpando GPIOs...")
    finally:
        if h is not None:
            lgpio.tx_pwm(h, PIN_LED, 100, 0.0)
            lgpio.tx_pwm(h, PIN_SERVO, 50, 0.0)
            lgpio.gpio_write(h, PIN_BUZZER, 0)
            lgpio.gpiochip_close(h)

if __name__ == '__main__':
    setup_hardware()
    metronome_loop()