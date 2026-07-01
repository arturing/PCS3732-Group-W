import subprocess
import re
import csv
import platform

# Configurações do compilador e executável
C_FILE = "benchmark.c"
EXEC_FILE = "./calculadora"
if platform.system() == "Windows":
    EXEC_FILE = "calculadora.exe"

def int_to_bin_str(value, num_bits):
    """Converte um inteiro (com sinal) para string binária de num_bits dígitos."""
    if value < 0:
        value = value & ((1 << num_bits) - 1)
    return format(value, f'0{num_bits}b')

def gerar_casos_do_script(bits):
    """
    Gera exatamente os 15 casos originais (5 Mul, 5 Div, 5 Fat).
    A lógica max_val = MAX_SIGNED baseia-se na do test_calculator.py.
    """
    max_val = (1 << (bits - 1)) - 1
    testes = []

    # --- 5 testes de MULTIPLICAÇÃO ---
    a_fixo = max_val
    for offset in range(4, -1, -1):
        testes.append(("mul", "*", a_fixo, max_val - offset))

    # --- 5 testes de DIVISÃO ---
    for b in range(1, 6):
        testes.append(("div", "/", max_val, b))

    # --- 5 testes de FATORIAL ---
    for offset in range(4, -1, -1):
        testes.append(("fact", "!", max_val - offset, 0))

    return testes

def compilar_codigo():
    print(f"[*] Compilando {C_FILE}...")
    result = subprocess.run(["gcc", C_FILE, "-o", "calculadora"], capture_output=True, text=True)
    if result.returncode != 0:
        print("[ERRO] Falha na compilação:\n", result.stderr)
        exit(1)
    print("[*] Compilação concluída com sucesso.\n")

def rodar_benchmark_e_gerar_csvs():
    arquiteturas = [4, 8, 16]
    
    for bits in arquiteturas:
        resultados = []
        testes = gerar_casos_do_script(bits)
        
        print(f"[*] Executando testes para arquitetura de {bits} bits...")
        
        for i, (op_name, opcode, a, b) in enumerate(testes):
            a_bin = int_to_bin_str(a, bits)
            b_bin = int_to_bin_str(b, bits)
            
            entrada_str = f"{a_bin} {opcode} {b_bin}"
            
            # Abre o executável C simulando a quantidade de bits desejada
            process = subprocess.Popen(
                [EXEC_FILE, str(bits)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, _ = process.communicate(input=entrada_str + "\n")
            
            # Valores Padrão
            res_dec = ""
            res_bin = ""
            overflow = False
            
            # 1. Tenta extrair o resultado Decimal
            m_dec = re.search(r"Decimal:\s*(-?\d+)", stdout)
            if m_dec:
                res_dec = m_dec.group(1)
            else:
                m_div = re.search(r"Resultado \(Divisao\):\s*([0-9.]+)", stdout)
                if m_div:
                    res_dec = m_div.group(1)
                else:
                    m_fat = re.search(r"Resultado Fatorial \(!\):\s*(\d+)", stdout)
                    if m_fat:
                        res_dec = m_fat.group(1)
            
            # 2. Tenta extrair o resultado Binário
            m_bin = re.search(r"Binario[^:]*:\s*([01]+)", stdout)
            if m_bin:
                res_bin = m_bin.group(1)
            else:
                # Se o C não gerar (ex: floats ou fatorial puro), o Python faz o bypass para o CSV
                if res_dec and "." not in res_dec:
                    try:
                        res_bin = int_to_bin_str(int(res_dec), bits)
                    except ValueError:
                        res_bin = ""
                        
            # 3. Detecta Overflow logicamente
            if "OVERFLOW" in stdout or "divisao por zero" in stdout.lower() or "abortada" in stdout.lower():
                overflow = True
            else:
                max_unsigned = (1 << bits) - 1
                if res_dec and "." not in res_dec:
                    try:
                        if int(res_dec) > max_unsigned or int(res_dec) < 0:
                            overflow = True
                    except ValueError:
                        pass
                        
            # 4. Extrai Tempo em ns e converte para us
            m_time = re.search(r"\[BENCHMARK\] Tempo:\s*(\d+)", stdout)
            if m_time:
                tempo_ns = int(m_time.group(1))
                tempo_us = round(tempo_ns / 1000.0, 3) # Conversão idêntica ao do ESP32
            else:
                tempo_us = "ERRO"
                
            # Prepara a linha para inserção
            resultados.append({
                "operacao": op_name,
                "num_bits": bits,
                "a_dec": a,
                "b_dec": b,
                "a_bin": a_bin,
                "b_bin": b_bin,
                "res_dec": res_dec,
                "res_bin": res_bin,
                "overflow": overflow,
                "tempo_us": tempo_us,
            })

        # Salva o CSV específico para esta arquitetura (mesma assinatura do test_calculator.py)
        output_csv = f"resultados_{bits}bits.csv"
        fieldnames = ["operacao", "num_bits", "a_dec", "b_dec", "a_bin", "b_bin",
                      "res_dec", "res_bin", "overflow", "tempo_us"]
        
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(resultados)
            
        print(f"    -> Arquivo '{output_csv}' gerado com sucesso!")

if __name__ == "__main__":
    compilar_codigo()
    rodar_benchmark_e_gerar_csvs()
