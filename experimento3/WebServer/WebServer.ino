#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>

#include "secrets.h"
#include "builtinfiles.h"

// Retornamos para apenas 4 pinos de LEDs seguros para a ESP32 DevKit
// Eles exibirão os 4 bits menos significativos (LSB) do resultado de 16 bits
const int LED_PINS[] = {12, 13, 14, 27}; 

WebServer server(80);

const char CALCULATOR_HTML[] PROGMEM = R"=====(
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Calculadora 16-Bits ESP32 (4 LEDs)</title>
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
        <h2>Painel Aritmético (16 Bits)</h2>
        <div class="input-group">
            <label>Operando A (16 bits binários):</label>
            <input type="text" id="valA" maxlength="16" value="0000000000000000">
        </div>
        <div class="input-group">
            <label>Operando B (16 bits binários):</label>
            <input type="text" id="valB" maxlength="16" value="0000000000000000">
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
        function enviarOperacao(op) {
            const a = document.getElementById('valA').value;
            let b = document.getElementById('valB').value;
            
            if (op === 'fact') {
                b = "0000000000000000"; 
            }

            // Validação mantém a exigência de 16 bits na interface web
            if(!/^[01]{16}$/.test(a) || !/^[01]{16}$/.test(b)) {
                alert("Por favor, insira exatamente 16 bits (0 ou 1).");
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
                        document.getElementById('status').innerText = (op === 'div' && b === "0000000000000000") ? "⚠️ ERRO: Divisão por Zero!" : "⚠️ OVERFLOW!";
                    } else {
                        document.getElementById('status').innerText = "✅ Sucesso";
                    }
                });
        }
    </script>
</body>
</html>
)=====";

// Lógica de Multiplicação (32 bits para processamento seguro)
int32_t multiply(int16_t a, int16_t b) {
    int32_t result = 0;
    bool isNegative = (b < 0);
    int32_t iter = isNegative ? -b : b;
    
    for (int32_t i = 0; i < iter; i++) {
        result += a;
    }
    return isNegative ? -result : result;
}

// Lógica de Fatorial
int32_t factorial(int16_t n) {
    if (n <= 1) return 1;
    int32_t result = 1;
    for(int16_t i = 2; i <= n; i++) {
        result *= i;
    }
    return result;
}

// Conversão tratando o bit de sinal de 16 bits (bit 15)
int16_t converterBinarioParaInteiro(String bin) {
    int32_t valor = strtol(bin.c_str(), NULL, 2);
    if (valor & 0x8000) {
        return (int16_t)(valor | 0xFFFF0000); 
    }
    return (int16_t)valor;
}

void handleCalculadora() {
    String paramA = server.arg("a");
    String paramB = server.arg("b");
    String operacao = server.arg("op");

    int16_t a = converterBinarioParaInteiro(paramA);
    int16_t b = converterBinarioParaInteiro(paramB);
    
    int32_t resultado = 0; 
    bool overflow = false;

    if (operacao == "add") {
        resultado = (int32_t)a + b;
    } else if (operacao == "sub") {
        resultado = (int32_t)a - b;
    } else if (operacao == "mul") {
        resultado = multiply(a, b);
    } else if (operacao == "div") {
        if (b == 0) {
            overflow = true;
            resultado = 0; 
        } else {
            resultado = (int32_t)a / b; 
        }
    } else if (operacao == "fact") {
        if (a < 0) {
             overflow = true;
             resultado = 0;
        } else {
             resultado = factorial(a);
        }
    }

    // Validação estrita baseada nos limites de 16 bits assinados (-32768 a 32767)
    if (resultado < -32768 || resultado > 32767) {
        overflow = true;
    }

    uint16_t bitsExibicao = resultado & 0xFFFF;
    int16_t resDecExibicao = (int16_t)bitsExibicao;

    // ESCALAMENTO DE HARDWARE ATENUADO:
    // Atualiza apenas os 4 LEDs físicos com os 4 bits menos significativos (LSB)
    for (int i = 0; i < 4; i++) {
        digitalWrite(LED_PINS[i], (bitsExibicao >> i) & 0x01);
    }

    // A interface Web (JSON) continua a receber a string completa de 16 bits
    String binString = "";
    for (int i = 15; i >= 0; i--) {
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
    for (int i = 0; i < 4; i++) {
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
        server.send(200, "text/html", CALCULATOR_HTML);
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