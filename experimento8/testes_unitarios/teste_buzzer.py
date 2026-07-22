#!/usr/bin/env python3
"""
Degrau 4: Teste Unitário do Buzzer
Verifica as chamadas bloqueantes e comportamento do pino digital.
"""
import lgpio
import time

PIN_BUZZER = 12

def main():
    print("--- Teste do Buzzer ---")
    h = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(h, PIN_BUZZER, level=0)
    
    try:
        print("Bipe Curto (150ms) - Simulando Sucesso")
        lgpio.gpio_write(h, PIN_BUZZER, 1)
        time.sleep(0.15)
        lgpio.gpio_write(h, PIN_BUZZER, 0)
        
        time.sleep(1)
        
        print("Bipe Longo (800ms) - Simulando Falha")
        lgpio.gpio_write(h, PIN_BUZZER, 1)
        time.sleep(0.8)
        lgpio.gpio_write(h, PIN_BUZZER, 0)
        
        time.sleep(1)
        
        print("Padrão Intermitente (3 bipes) - Simulando Alarme")
        for _ in range(3):
            lgpio.gpio_write(h, PIN_BUZZER, 1)
            time.sleep(0.2)
            lgpio.gpio_write(h, PIN_BUZZER, 0)
            time.sleep(0.2)
            
    except KeyboardInterrupt:
        pass
    finally:
        print("Encerrando teste.")
        lgpio.gpio_write(h, PIN_BUZZER, 0)
        lgpio.gpiochip_close(h)

if __name__ == '__main__':
    main()
