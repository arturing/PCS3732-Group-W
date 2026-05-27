#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>

#include "secrets.h"
#include "builtinfiles.h"

const int LED_PINS[] = {7, 6, 5, 4}; 

WebServer server(80);

const char CALCULATOR_HTML[] PROGMEM = R"=====(
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Calculadora 4-Bits ESP32</title>
    <style>
        body { font-family: 'Segoe UI', Arial, sans-serif; background: #1e293b; color: #f8fafc; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .card { background: #0f172a; padding: 30px; border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.5); width: 100%; max-width: 360px; text-align: center; }
        h2 { margin-bottom: 20px; color: #38bdf8; }
        .input-group { margin-bottom: 15px; text-align: left; }
        label { display: block; margin-bottom: 5px; font-size: 0.9em; color: #94a3b8; }
        input { width: 100%; padding: 10px; border: 1px solid #334155; background: #1e293b; color: #fff; border-radius: 6px; font-family: monospace; font-size: 1.2em; text-align: center; box-sizing: border-box; }
        .btn-group { display: flex; gap: 10px; margin-top: 20px; }
        button { flex: 1; padding: 12px; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; transition: 0.2s; }
        .btn-add { background: #10b981; color: white; }
        .btn-sub { background: #ef4444; color: white; }
        button:hover { opacity: 0.9; }
        #output { margin-top: 20px; padding: 15px; border-radius: 6px; display: none; background: #1e293b; border-left: 5px solid #38bdf8; }
        .overflow { border-left-color: #ef4444 !important; background: #451a03 !important; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Painel Aritmético</h2>
        <div class="input-group">
            <label>Operando A (4 bits binários):</label>
            <input type="text" id="valA" maxlength="4" value="0000">
        </div>
        <div class="input-group">
            <label>Operando B (4 bits binários):</label>
            <input type="text" id="valB" maxlength="4" value="0000">
        </div>
        <div class="btn-group">
            <button class="btn-add" onclick="enviarOperacao('add')">SOMAR</button>
            <button class="btn-sub" onclick="enviarOperacao('sub')">SUBTRAIR</button>
        </div>
        <div id="output">
            <div id="resDec"></div>
            <div id="resBin" style="font-weight:bold; font-size:1.1em; margin: 5px 0;"></div>
            <div id="status"></div>
        </div>
    </div>
    <script>
        function enviarOperacao(op) {
            const a = document.getElementById('valA').value;
            const b = document.getElementById('valB').value;
            if(!/^[01]{4}$/.test(a) || !/^[01]{4}$/.test(b)) {
                alert("Por favor, insira exatamente 4 bits (0 ou 1).");
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
                    document.getElementById('status').innerText = data.overflow ? "⚠️ OVERFLOW!" : "✅ Sucesso";
                });
        }
    </script>
</body>
</html>
)=====";

int8_t converterBinarioParaInteiro(String bin) {
    int valor = strtol(bin.c_str(), NULL, 2);
    if (valor & 0x08) {
        return (int8_t)(valor | 0xF0); 
    }
    return (int8_t)valor;
}

void handleCalculadora() {
    String paramA = server.arg("a");
    String paramB = server.arg("b");
    String operacao = server.arg("op");

    int8_t a = converterBinarioParaInteiro(paramA);
    int8_t b = converterBinarioParaInteiro(paramB);
    int8_t resultado = 0;
    bool overflow = false;

    if (operacao == "add") {
        resultado = a + b;
    } else if (operacao == "sub") {
        resultado = a - b;
    }

    if (resultado < -8 || resultado > 7) {
        overflow = true;
    }

    int bitsExibicao = resultado & 0x0F;

    int8_t resDecExibicao = bitsExibicao;
    if (resDecExibicao & 0x08) {
        resDecExibicao |= 0xF0; 
    }

    for (int i = 0; i < 4; i++) {
        digitalWrite(LED_PINS[i], (bitsExibicao >> i) & 0x01);
    }

    String jsonResponse = "{";
    jsonResponse += "\"resDec\":" + String(resDecExibicao) + ",";
    jsonResponse += "\"resBin\":\"" + String((bitsExibicao >> 3) & 1) + String((bitsExibicao >> 2) & 1) + 
                    String((bitsExibicao >> 1) & 1) + String(bitsExibicao & 1) + "\",";
    jsonResponse += "\"overflow\":" + String(overflow ? "true" : "false");
    jsonResponse += "}";

    server.send(200, "application/json", jsonResponse);
}

void setup() {
    Serial.begin(115200);

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