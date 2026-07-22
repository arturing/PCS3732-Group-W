#!/usr/bin/env python3
"""
Degrau 2: Teste Unitário do Teclado Matricial 4x4
Verifica a varredura e o debouncing (anti-bouncing).
"""
import lgpio
import time

PIN_ROWS = [5, 6, 13, 19]
PIN_COLS = [12, 16, 20, 21]

KEYPAD_MAP = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D'],
]

KEY_DEBOUNCE_TIME = 0.05

def main():
    print("--- Teste do Teclado 4x4 ---")
    h = lgpio.gpiochip_open(0)
    
    for pin in PIN_ROWS:
        lgpio.gpio_claim_output(h, pin, level=1)
    for pin in PIN_COLS:
        lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_UP)

    last_key = None
    last_key_time = 0.0

    try:
        while True:
            now = time.time()
            current_key = None

            for row_idx, row_pin in enumerate(PIN_ROWS):
                lgpio.gpio_write(h, row_pin, 0)
                time.sleep(0.001)

                for col_idx, col_pin in enumerate(PIN_COLS):
                    if lgpio.gpio_read(h, col_pin) == 0:
                        current_key = KEYPAD_MAP[row_idx][col_idx]
                        break

                lgpio.gpio_write(h, row_pin, 1)
                if current_key:
                    break

            if current_key:
                if current_key != last_key or (now - last_key_time) >= KEY_DEBOUNCE_TIME:
                    print(f"Tecla Pressionada: {current_key}")
                    last_key = current_key
                    last_key_time = now
            elif (now - last_key_time) >= KEY_DEBOUNCE_TIME:
                last_key = None
                
            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nEncerrando teste.")
    finally:
        lgpio.gpiochip_close(h)

if __name__ == '__main__':
    main()
