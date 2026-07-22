#!/usr/bin/env python3
"""
Degrau 1: Teste Unitário do Sensor Ultrassônico HC-SR04
Verifica a leitura contínua de distâncias (polling).
"""
import lgpio
import time

PIN_TRIG = 23
PIN_ECHO = 24
SPEED_OF_SOUND_CM_PER_S = 34300.0
TIMEOUT_S = 0.04

def medir_distancia(h):
    # TRIG LOW
    lgpio.gpio_write(h, PIN_TRIG, 0)
    time.sleep(0.002)

    # Pulso 10us
    lgpio.gpio_write(h, PIN_TRIG, 1)
    time.sleep(0.00001)
    lgpio.gpio_write(h, PIN_TRIG, 0)

    # Aguarda borda de subida (ECHO)
    start = time.time()
    timeout_limit = start + TIMEOUT_S
    while lgpio.gpio_read(h, PIN_ECHO) == 0:
        start = time.time()
        if start > timeout_limit:
            return -1.0

    # Aguarda borda de descida
    end = start
    timeout_limit = end + TIMEOUT_S
    while lgpio.gpio_read(h, PIN_ECHO) == 1:
        end = time.time()
        if end > timeout_limit:
            return -1.0

    return ((end - start) * SPEED_OF_SOUND_CM_PER_S) / 2.0

def main():
    print("--- Teste do Sensor HC-SR04 ---")
    h = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(h, PIN_TRIG, level=0)
    lgpio.gpio_claim_input(h, PIN_ECHO)
    
    try:
        while True:
            dist = medir_distancia(h)
            if dist >= 0:
                print(f"Distância: {dist:.1f} cm")
            else:
                print("Timeout: Objeto fora de alcance.")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nEncerrando teste.")
    finally:
        lgpio.gpiochip_close(h)

if __name__ == '__main__':
    main()
