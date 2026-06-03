#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>

#include "secrets.h"
#include "builtinfiles.h"

// ======================== CONFIGURAÇÃO ========================
// Defina o número de bits da calculadora (2 a 32)
#define NUM_BITS 4
// ==============================================================

// Constantes derivadas de NUM_BITS
#define MAX_SIGNED_VAL  ((1 << (NUM_BITS - 1)) - 1)
#define MIN_SIGNED_VAL  (-(1 << (NUM_BITS - 1)))
#define BIT_MASK        ((1 << NUM_BITS) - 1)
#define SIGN_BIT        (1 << (NUM_BITS - 1))

// Retornamos para apenas 4 pinos de LEDs seguros para a ESP32 DevKit
// Eles exibirão os 4 bits menos significativos (LSB) do resultado
const int LED_PINS[] = {12, 13, 14, 27}; 
const int NUM_LEDS = 4;

WebServer server(80);

// Helper: gerar string de NUM_BITS zeros
String zeroString() {
    String s = "";
    s.reserve(NUM_BITS);
    for (int i = 0; i < NUM_BITS; i++) s += '0';
    return s;
}

// Template HTML com placeholders {{BITS}} e {{ZEROS}} substituídos em tempo de execução
const char CALCULATOR_HTML_TEMPLATE[] PROGMEM = R"=====(
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Calculadora {{BITS}}-Bits ESP32 (4 LEDs)</title>
    <style>
        body { font-family: 'Segoe UI', Arial, sans-serif; background: #1e293b; color: #f8fafc; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .card { background: #0f172a; padding: 30px; border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.5); width: 100%; max-width: 480px; text-align: center; }
        h2 { margin-bottom: 20px; color: #38bdf8; }
        .input-group { margin-bottom: 15px; text-align: left; }
        label { display: block; margin-bottom: 5px; font-size: 0.9em; color: #94a3b8; }
        input { width: 100%; padding: 10px; border: 1px solid #334155; background: #1e293b; color: #fff; border-radius: 6px; font-family: monospace; font-size: 1.1em; text-align: center; box-sizing: border-box; letter-spacing: 2px; }
        .btn-group { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }
        button { flex: 1 1 30%; padding: 10px; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s; font-size: 0.9em; }
        .btn-add { background: #10b981; color: white; }
        .btn-sub { background: #ef4444; color: white; }
        .btn-mul { background: #eab308; color: white; }
        .btn-div { background: #3b82f6; color: white; }
        .btn-fac { background: #8b5cf6; color: white; flex: 1 1 100%; }
        button:hover { opacity: 0.9; }
        #output { margin-top: 20px; padding: 15px; border-radius: 6px; display: none; background: #1e293b; border-left: 5px solid #38bdf8; }
        .overflow { border-left-color: #ef4444 !important; background: #451a03 !important; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Painel Aritmético ({{BITS}} Bits)</h2>
        <div class="input-group">
            <label>Operando A ({{BITS}} bits binários):</label>
            <input type="text" id="valA" maxlength="{{BITS}}" value="{{ZEROS}}">
        </div>
        <div class="input-group">
            <label>Operando B ({{BITS}} bits binários):</label>
            <input type="text" id="valB" maxlength="{{BITS}}" value="{{ZEROS}}">
        </div>
        <div class="btn-group">
            <button class="btn-add" onclick="enviarOperacao('add')">SOMAR</button>
            <button class="btn-sub" onclick="enviarOperacao('sub')">SUBTRAIR</button>
            <button class="btn-mul" onclick="enviarOperacao('mul')">MULTIPLICAR</button>
            <button class="btn-div" onclick="enviarOperacao('div')">DIVIDIR</button>
            <button class="btn-fac" onclick="enviarOperacao('fact')">FATORIAL (A!)</button>
        </div>
        <div id="output">
            <div id="resDec"></div>
            <div id="resBin" style="font-weight:bold; font-size:1.1em; margin: 5px 0; word-break: break-all;"></div>
            <div id="status"></div>
        </div>
    </div>
    <script>
        const NUM_BITS = {{BITS}};
        const ZEROS = "{{ZEROS}}";

        function enviarOperacao(op) {
            const a = document.getElementById('valA').value;
            let b = document.getElementById('valB').value;
            
            if (op === 'fact') {
                b = ZEROS; 
            }

            // Validação dinâmica baseada em NUM_BITS
            const regex = new RegExp("^[01]{" + NUM_BITS + "}$");
            if(!regex.test(a) || !regex.test(b)) {
                alert("Por favor, insira exatamente " + NUM_BITS + " bits (0 ou 1).");
                return;
            }
            fetch(`/calc?a=${a}&b=${b}&op=${op}`)
                .then(res => res.json())
                .then(data => {
                    const out = document.getElementById('output');
                    out.style.display = 'block';
                    if(data.overflow) { out.classList.add('overflow'); } 
                    else { out.classList.remove('overflow'); }
                    
                    document.getElementById('resDec').innerText = "Resultado Decimal: " + data.resDec;
                    document.getElementById('resBin').innerText = "Resultado Binário: " + data.resBin;
                    
                    if(data.overflow) {
                        document.getElementById('status').innerText = (op === 'div' && b === ZEROS) ? "⚠️ ERRO: Divisão por Zero!" : "⚠️ OVERFLOW!";
                    } else {
                        document.getElementById('status').innerText = "✅ Sucesso";
                    }
                });
        }
    </script>
</body>
</html>
)=====";

// Lógica de Multiplicação (64 bits para processamento seguro)
int64_t multiply(int32_t a, int32_t b) {
    int64_t result = 0;
    bool isNegative = (b < 0);
    int64_t iter = isNegative ? -(int64_t)b : (int64_t)b;
    
    for (int64_t i = 0; i < iter; i++) {
        result += a;
    }
    return isNegative ? -result : result;
}

// Lógica de Fatorial
int64_t factorial(int32_t n) {
    if (n <= 1) return 1;
    int64_t result = 1;
    for(int32_t i = 2; i <= n; i++) {
        result *= i;
    }
    return result;
}

// Conversão tratando o bit de sinal de NUM_BITS bits
int32_t converterBinarioParaInteiro(String bin) {
    uint32_t valor = strtoul(bin.c_str(), NULL, 2);
    valor &= BIT_MASK;
    if (valor & SIGN_BIT) {
        // Extensão de sinal para 32 bits
        return (int32_t)(valor | ~BIT_MASK);
    }
    return (int32_t)valor;
}

void handleCalculadora() {
    String paramA = server.arg("a");
    String paramB = server.arg("b");
    String operacao = server.arg("op");

    int32_t a = converterBinarioParaInteiro(paramA);
    int32_t b = converterBinarioParaInteiro(paramB);
    
    int64_t resultado = 0; 
    bool overflow = false;

    if (operacao == "add") {
        resultado = (int64_t)a + b;
    } else if (operacao == "sub") {
        resultado = (int64_t)a - b;
    } else if (operacao == "mul") {
        resultado = multiply(a, b);
    } else if (operacao == "div") {
        if (b == 0) {
            overflow = true;
            resultado = 0; 
        } else {
            resultado = (int64_t)a / b; 
        }
    } else if (operacao == "fact") {
        if (a < 0) {
             overflow = true;
             resultado = 0;
        } else {
             resultado = factorial(a);
        }
    }

    // Validação baseada nos limites de NUM_BITS bits assinados
    if (resultado < MIN_SIGNED_VAL || resultado > MAX_SIGNED_VAL) {
        overflow = true;
    }

    // Trunca o resultado para NUM_BITS
    uint32_t bitsExibicao = (uint32_t)(resultado & BIT_MASK);

    // Interpreta o valor truncado como signed para exibição decimal
    int32_t resDecExibicao;
    if (bitsExibicao & SIGN_BIT) {
        resDecExibicao = (int32_t)(bitsExibicao | ~BIT_MASK);
    } else {
        resDecExibicao = (int32_t)bitsExibicao;
    }

    // ESCALAMENTO DE HARDWARE ATENUADO:
    // Atualiza apenas os 4 LEDs físicos com os 4 bits menos significativos (LSB)
    for (int i = 0; i < NUM_LEDS; i++) {
        digitalWrite(LED_PINS[i], (bitsExibicao >> i) & 0x01);
    }

    // A interface Web (JSON) recebe a string completa de NUM_BITS bits
    String binString = "";
    for (int i = NUM_BITS - 1; i >= 0; i--) {
        binString += String((bitsExibicao >> i) & 1);
    }

    String jsonResponse = "{";
    jsonResponse += "\"resDec\":" + String(resDecExibicao) + ",";
    jsonResponse += "\"resBin\":\"" + binString + "\",";
    jsonResponse += "\"overflow\":" + String(overflow ? "true" : "false");
    jsonResponse += "}";

    server.send(200, "application/json", jsonResponse);
}

void setup() {
    Serial.begin(115200);

    // Inicializa apenas os 4 pinos de saída físicos
    for (int i = 0; i < NUM_LEDS; i++) {
        pinMode(LED_PINS[i], OUTPUT);
        digitalWrite(LED_PINS[i], LOW);
    }

    Serial.print("Configurando Ponto de Acesso: ");
    Serial.println(ssid);
    WiFi.softAP(ssid, passPhrase); 

    Serial.println("\nWi-Fi Criado!");
    Serial.print("Endereço IP do ESP32: ");
    Serial.println(WiFi.softAPIP());
    
    server.on("/", HTTP_GET, []() {
        String html = FPSTR(CALCULATOR_HTML_TEMPLATE);
        String zeros = zeroString();
        html.replace("{{BITS}}", String(NUM_BITS));
        html.replace("{{ZEROS}}", zeros);
        server.send(200, "text/html", html);
    });

    server.on("/calc", HTTP_GET, handleCalculadora);

    server.onNotFound([]() {
        server.send(404, "text/html", FPSTR(notFoundContent));
    });

    server.begin();
    Serial.println("Servidor Web HTTP ativo na porta 80");
}

void loop() {
    server.handleClient();
}