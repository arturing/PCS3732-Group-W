#!/usr/bin/env python3
"""
Degrau 2: Teste Unitário do Teclado Matricial 4x4 (Versão PULL-DOWN)
Implementa a exata lógica validada na Experiência 6, traduzida para lgpio.
"""
import lgpio
import time
import argparse

PIN_ROWS = [16, 20, 21, 26]
PIN_COLS = [19, 13, 6, 5]

KEYPAD_MAP = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D'],
]

SETTLE_S = 0.00005
DEBOUNCE_S = 0.04

class KeypadTest:
    def __init__(self, h):
        self.h = h
        self._held = None
        self._t_release = 0.0
        
        for pin in PIN_ROWS:
            lgpio.gpio_claim_output(self.h, pin, level=0)
        for pin in PIN_COLS:
            lgpio.gpio_claim_input(self.h, pin, lgpio.SET_PULL_DOWN)

    def scan_raw(self):
        for ri, r in enumerate(PIN_ROWS):
            lgpio.gpio_write(self.h, r, 1)
            time.sleep(SETTLE_S)
            for ci, c in enumerate(PIN_COLS):
                if lgpio.gpio_read(self.h, c) == 1:
                    lgpio.gpio_write(self.h, r, 0)
                    return KEYPAD_MAP[ri][ci]
            lgpio.gpio_write(self.h, r, 0)
        return None

    def get_event(self):
        k = self.scan_raw()
        agora = time.time()
        if k is not None:
            if self._held is None and (agora - self._t_release) >= DEBOUNCE_S:
                self._held = k
                return k
            return None
        if self._held is not None:
            self._held = None
            self._t_release = agora
        return None

    def diagnostico_repouso(self):
        print("== Diagnostico (NAO aperte nada agora) ==")
        suspeita = False
        for c in PIN_COLS:
            v = lgpio.gpio_read(self.h, c)
            aviso = "  <-- DEVERIA SER 0! (pull-down falhou)" if v == 1 else ""
            print(f"  coluna GPIO{c:>2} em repouso = {v}{aviso}")
            suspeita = suspeita or (v == 1)
        if suspeita:
            print("\n>> Alguma coluna leu 1 sem tecla: pull-down inativo nela.")
            print(">> Fixe no /boot/firmware/config.txt se preciso!\n")
        else:
            print("\n>> Repouso OK (tudo em 0).\n")
        return not suspeita

def main():
    p = argparse.ArgumentParser(description="Teste isolado do teclado 4x4.")
    p.add_argument("--diag", action="store_true", help="So diagnostico.")
    args = p.parse_args()

    h = lgpio.gpiochip_open(0)
    kp = KeypadTest(h)
    
    print(f"==== Teste de Teclado Matricial (Exp 8) ====")
    print(f"     linhas (saidas)  BCM: {PIN_ROWS}")
    print(f"     colunas (entrada) BCM: {PIN_COLS}\n")
    try:
        kp.diagnostico_repouso()
        if args.diag:
            return
            
        print(">> Pressione teclas (Ctrl+C para sair):\n")
        while True:
            k = kp.get_event()
            if k is not None:
                print(f"   tecla = '{k}'")
            time.sleep(0.005)
    except KeyboardInterrupt:
        print("\nInterrompido.")
    finally:
        for r in PIN_ROWS:
            lgpio.gpio_write(h, r, 0)
        lgpio.gpiochip_close(h)

if __name__ == "__main__":
    main()
