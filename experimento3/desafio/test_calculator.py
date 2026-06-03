import serial
import requests
import csv
import time
import subprocess
import sys
import platform
import os

# ======================== CONFIGURAÇÃO ========================
NUM_BITS = 16                       # Deve corresponder ao NUM_BITS do firmware
COM_PORT = "COM5" if platform.system() == "Windows" else "/dev/ttyUSB0"  # Porta serial do ESP32
BAUD_RATE = 115200
ESP32_IP = "192.168.4.1"
WIFI_SSID = "toner"              # Altere para o SSID do seu AP
WIFI_PASSWORD = "toner123"          # Altere para a senha do seu AP
OUTPUT_CSV = f"resultados_{NUM_BITS}bits.csv"
# ==============================================================

MAX_SIGNED = (1 << (NUM_BITS - 1)) - 1
MIN_SIGNED = -(1 << (NUM_BITS - 1))
BIT_MASK = (1 << NUM_BITS) - 1


def int_to_bin_str(value, num_bits):
    """Converte um inteiro (com sinal) para string binária de num_bits dígitos."""
    if value < 0:
        value = value & ((1 << num_bits) - 1)
    return format(value, f'0{num_bits}b')


def connect_wifi_windows(ssid, password):
    """Conecta ao AP do ESP32 via netsh (Windows)."""
    profile_xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig>
        <SSID>
            <name>{ssid}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>manual</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{password}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>"""

    profile_path = "temp_wifi_profile.xml"
    with open(profile_path, "w") as f:
        f.write(profile_xml)

    try:
        subprocess.run(["netsh", "wlan", "add", "profile", f"filename={profile_path}"],
                       capture_output=True, check=True)
        subprocess.run(["netsh", "wlan", "connect", f"name={ssid}"],
                       capture_output=True, check=True)
    finally:
        os.remove(profile_path)

    for i in range(15):
        result = subprocess.run(["netsh", "wlan", "show", "interfaces"],
                                capture_output=True, text=True)
        if ssid in result.stdout and "connected" in result.stdout.lower():
            return True
        time.sleep(1)
    return False


def connect_wifi_linux(ssid, password):
    """Conecta ao AP do ESP32 via nmcli (Linux)."""
    # Remove conexão anterior com mesmo SSID, se existir
    subprocess.run(["nmcli", "connection", "delete", ssid],
                   capture_output=True)

    result = subprocess.run(
        ["nmcli", "device", "wifi", "connect", ssid, "password", password],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        return True

    # Aguarda caso esteja conectando
    for i in range(15):
        result = subprocess.run(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"],
                                capture_output=True, text=True)
        if f"yes:{ssid}" in result.stdout.lower():
            return True
        time.sleep(1)
    return False


def connect_wifi(ssid, password):
    """Conecta ao AP do ESP32 (Windows ou Linux)."""
    print(f"Conectando ao Wi-Fi '{ssid}'...")

    if platform.system() == "Windows":
        ok = connect_wifi_windows(ssid, password)
    else:
        ok = connect_wifi_linux(ssid, password)

    if ok:
        print(f"Conectado ao '{ssid}'!")
    else:
        print("ERRO: Não foi possível conectar ao AP.")
    return ok


def generate_test_cases(num_bits):
    """Gera 5 casos de teste para mul, div e fact."""
    max_val = MAX_SIGNED

    tests = []

    # --- 5 testes de MULTIPLICAÇÃO ---
    # A fixo = MAX, B = max-4, max-3, max-2, max-1, max
    # O loop de multiplicação itera |B| vezes, então B grande = mais tempo
    a_fixo = max_val
    for offset in range(4, -1, -1):
        tests.append(("mul", a_fixo, max_val - offset))

    # --- 5 testes de DIVISÃO ---
    # A = MAX (dividendo grande), B = 1..5 (divisor pequeno = quociente grande)
    # Divisão 64-bit em software: mais bits no quociente = mais passos
    for b in range(1, 6):
        tests.append(("div", max_val, b))

    # --- 5 testes de FATORIAL ---
    # A = max-4, max-3, max-2, max-1, max
    for offset in range(4, -1, -1):
        tests.append(("fact", max_val - offset, 0))

    return tests


def run_tests():
    """Executa os testes e grava os resultados em CSV."""
    test_cases = generate_test_cases(NUM_BITS)

    # Abre a porta serial
    print(f"Abrindo porta serial {COM_PORT} a {BAUD_RATE} baud...")
    ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=2)
    time.sleep(2)  # Aguarda reset do ESP32
    ser.reset_input_buffer()

    # Conecta ao Wi-Fi
    # if not connect_wifi(WIFI_SSID, WIFI_PASSWORD):
    #     ser.close()
    #     sys.exit(1)

    time.sleep(2)  # Aguarda estabilização da rede
    base_url = f"http://{ESP32_IP}/calc"

    results = []

    for i, (op, a, b) in enumerate(test_cases):
        a_bin = int_to_bin_str(a, NUM_BITS)
        b_bin = int_to_bin_str(b, NUM_BITS)

        print(f"\n[{i+1}/{len(test_cases)}] {op.upper()}: A={a} ({a_bin}), B={b} ({b_bin})")

        # Limpa buffer serial antes do request
        ser.reset_input_buffer()

        try:
            resp = requests.get(base_url, params={"a": a_bin, "b": b_bin, "op": op}, timeout=10)
            data = resp.json()
        except Exception as e:
            print(f"  ERRO HTTP: {e}")
            results.append({
                "operacao": op, "a_dec": a, "b_dec": b,
                "a_bin": a_bin, "b_bin": b_bin,
                "res_dec": "ERRO", "res_bin": "ERRO",
                "overflow": "ERRO", "tempo_us": "ERRO"
            })
            continue

        # Lê a linha de tempo do serial
        tempo_us = ""
        time.sleep(0.3)  # Aguarda dados no buffer serial
        while ser.in_waiting:
            line = ser.readline().decode("utf-8", errors="replace").strip()
            if " us" in line:
                # Extrai o valor numérico (ex: "Multiplicação: 42 us" → "42")
                parts = line.split(":")
                if len(parts) >= 2:
                    tempo_us = parts[1].strip().replace(" us", "")
                break

        print(f"  Resultado: {data.get('resDec')} | Bin: {data.get('resBin')} | "
              f"Overflow: {data.get('overflow')} | Tempo: {tempo_us} us")

        results.append({
            "operacao": op,
            "num_bits": NUM_BITS,
            "a_dec": a,
            "b_dec": b,
            "a_bin": a_bin,
            "b_bin": b_bin,
            "res_dec": data.get("resDec"),
            "res_bin": data.get("resBin"),
            "overflow": data.get("overflow"),
            "tempo_us": tempo_us,
        })

    ser.close()

    # Grava CSV
    fieldnames = ["operacao", "num_bits", "a_dec", "b_dec", "a_bin", "b_bin",
                  "res_dec", "res_bin", "overflow", "tempo_us"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n{'='*50}")
    print(f"Resultados salvos em: {OUTPUT_CSV}")
    print(f"Total de testes: {len(results)}")


if __name__ == "__main__":
    run_tests()
