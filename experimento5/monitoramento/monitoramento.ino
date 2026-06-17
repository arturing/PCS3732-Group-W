#include <WiFi.h>
#include <WebServer.h>

const char* ssid     = "toner";
const char* password = "toner123";

WebServer server(80);

const int PIN_LDR = 36;
const int PIN_BOTAO_SOS = 26;
const int PIN_LED_R = 32;
const int PIN_LED_G = 33;
const int PIN_LED_B = 25;

const int LIMIAR_BAIXA_LUZ = 2000;

volatile int leituraLDR = 0;
unsigned long ultimaLeituraMs = 0;
const unsigned long INTERVALO_LDR = 1000;

// Interrupt debounce flag and timer
volatile bool sosAtivado = false;
volatile unsigned long ultimoDebounceMs = 0;
const unsigned long JANELA_DEBOUNCE = 200;

enum EstadoSistema {
  NORMAL,
  NOTURNO,
  EMERGENCIA
};

EstadoSistema estadoAtual = NORMAL;

unsigned long inicioEmergenciaMs = 0;
const unsigned long DURACAO_EMERGENCIA = 3000;

unsigned long ultimoPiscaMs = 0;
const unsigned long INTERVALO_PISCA = 2000;
bool ledAmareloLigado = false;

// SOS Button ISR (Hardware interrupt on FALLING edge)
void IRAM_ATTR isrBotaoSOS() {
  unsigned long agora = millis();
  // Software debounce
  if (agora - ultimoDebounceMs >= JANELA_DEBOUNCE) {
    sosAtivado = true;
    ultimoDebounceMs = agora;
  }
}

void ledApagar() {
  digitalWrite(PIN_LED_R, LOW);
  digitalWrite(PIN_LED_G, LOW);
  digitalWrite(PIN_LED_B, LOW);
  ledAmareloLigado = false;
}

void ledVermelho() {
  digitalWrite(PIN_LED_R, HIGH);
  digitalWrite(PIN_LED_G, LOW);
  digitalWrite(PIN_LED_B, LOW);
}

void ledAmarelo() {
  digitalWrite(PIN_LED_R, HIGH);
  digitalWrite(PIN_LED_G, HIGH);
  digitalWrite(PIN_LED_B, LOW);
}

void handleRoot() {
  Serial.println("\n[WEB] Usuário acessou a página principal (/)");

  String html = "<!DOCTYPE html><html><head>";
  html += "<meta charset='UTF-8'>";
  html += "<meta name='viewport' content='width=device-width, initial-scale=1.0'>";
  html += "<title>ESP32 - Monitoramento Inteligente</title>";
  html += "<style>";
  html += "* { box-sizing: border-box; margin: 0; padding: 0; }";
  html += "body { font-family: 'Segoe UI', Arial, sans-serif; background: #1a1a2e; color: #e0e0e0; min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 30px 15px; }";
  html += "h1 { color: #00d4ff; font-size: 1.6em; margin-bottom: 25px; text-shadow: 0 0 10px rgba(0,212,255,0.3); }";
  html += ".card { background: #16213e; border-radius: 16px; padding: 25px; margin: 10px 0; width: 90%; max-width: 420px; box-shadow: 0 4px 20px rgba(0,0,0,0.4); border: 1px solid #0f3460; }";
  html += ".card h2 { font-size: 1.1em; color: #a0a0d0; margin-bottom: 15px; }";
  html += ".ldr-value { font-size: 3em; font-weight: bold; color: #00d4ff; text-align: center; }";
  html += ".ldr-bar { width: 100%; height: 12px; background: #0f3460; border-radius: 6px; margin-top: 12px; overflow: hidden; }";
  html += ".ldr-fill { height: 100%; border-radius: 6px; transition: width 0.5s ease, background 0.5s ease; }";
  html += ".status { text-align: center; font-size: 1.3em; padding: 12px; border-radius: 10px; margin-top: 10px; font-weight: bold; }";
  html += ".status.normal { background: #1b4332; color: #52b788; }";
  html += ".status.noturno { background: #433500; color: #ffc300; }";
  html += ".status.emergencia { background: #641220; color: #e5383b; animation: pulse 1s infinite; }";
  html += "@keyframes pulse { 0%,100%{ opacity:1; } 50%{ opacity:0.6; } }";
  html += ".info { font-size: 0.85em; color: #7a7aaa; margin-top: 8px; text-align: center; }";
  html += "</style></head><body>";

  html += "<h1>&#128161; Monitoramento Inteligente</h1>";

  html += "<div class='card'>";
  html += "<h2>&#9728;&#65039; Sensor de Luminosidade (LDR)</h2>";
  html += "<div class='ldr-value' id='ldrVal'>---</div>";
  html += "<div class='ldr-bar'><div class='ldr-fill' id='ldrBar' style='width:0%; background:#00d4ff;'></div></div>";
  html += "<div class='info'>Resolução ADC: 12 bits (0–4095) | Atualização: 1 Hz</div>";
  html += "</div>";

  html += "<div class='card'>";
  html += "<h2>&#128226; Estado do Sistema</h2>";
  html += "<div class='status normal' id='sysStatus'>Carregando...</div>";
  html += "</div>";

  html += "<script>";
  html += "function atualizarDados() {";
  html += "  fetch('/dados').then(r => r.json()).then(d => {";
  html += "    document.getElementById('ldrVal').textContent = d.ldr;";
  html += "    var pct = (d.ldr / 4095 * 100).toFixed(1);";
  html += "    var bar = document.getElementById('ldrBar');";
  html += "    bar.style.width = pct + '%';";
  html += "    if(d.ldr > " + String(LIMIAR_BAIXA_LUZ) + ") { bar.style.background='#ffc300'; }";
  html += "    else { bar.style.background='#00d4ff'; }";
  html += "    var st = document.getElementById('sysStatus');";
  html += "    if(d.estado == 'EMERGENCIA') { st.textContent='\\u26A0\\uFE0F EMERGENCIA SOS'; st.className='status emergencia'; }";
  html += "    else if(d.estado == 'NOTURNO') { st.textContent='\\uD83C\\uDF19 Modo Noturno'; st.className='status noturno'; }";
  html += "    else { st.textContent='\\u2705 Normal'; st.className='status normal'; }";
  html += "  }).catch(e => { console.error(e); });";
  html += "}";
  html += "atualizarDados();";
  html += "setInterval(atualizarDados, 1000);";
  html += "</script>";

  html += "</body></html>";

  server.send(200, "text/html", html);
}

void handleDados() {
  String estado;
  switch (estadoAtual) {
    case EMERGENCIA: estado = "EMERGENCIA"; break;
    case NOTURNO:    estado = "NOTURNO";    break;
    default:         estado = "NORMAL";     break;
  }

  String json = "{";
  json += "\"ldr\":" + String(leituraLDR) + ",";
  json += "\"limiar\":" + String(LIMIAR_BAIXA_LUZ) + ",";
  json += "\"estado\":\"" + estado + "\"";
  json += "}";

  server.send(200, "application/json", json);
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=============================================");
  Serial.println("--- BOOT: SISTEMA DE MONITORAMENTO ESP32 ---");
  Serial.println("=============================================");

  pinMode(PIN_LED_R, OUTPUT);
  pinMode(PIN_LED_G, OUTPUT);
  pinMode(PIN_LED_B, OUTPUT);
  ledApagar();
  Serial.println("[SETUP] LED RGB configurado.");

  analogReadResolution(12);
  Serial.print("[SETUP] LDR configurado no pino ADC ");
  Serial.println(PIN_LDR);

  pinMode(PIN_BOTAO_SOS, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_BOTAO_SOS), isrBotaoSOS, FALLING);
  Serial.print("[SETUP] Botão SOS configurado no pino ");
  Serial.print(PIN_BOTAO_SOS);
  Serial.println(" (interrupção FALLING, pull-up interno).");

  Serial.print("[REDE] Criando Hotspot: ");
  Serial.println(ssid);
  WiFi.softAP(ssid, password);

  IPAddress IP = WiFi.softAPIP();
  Serial.print("[REDE] Hotspot Pronto. IP do Dashboard: ");
  Serial.println(IP);

  server.on("/",      HTTP_GET, handleRoot);
  server.on("/dados", HTTP_GET, handleDados);

  server.begin();
  Serial.println("[SISTEMA] Servidor HTTP Online e aguardando conexões...\n");
}

void loop() {
  unsigned long agora = millis();

  // Non-blocking LDR reading
  if (agora - ultimaLeituraMs >= INTERVALO_LDR) {
    ultimaLeituraMs = agora;
    leituraLDR = analogRead(PIN_LDR);

    Serial.print("[LDR] Valor ADC: ");
    Serial.print(leituraLDR);
    if (leituraLDR > LIMIAR_BAIXA_LUZ) {
      Serial.println(" (BAIXA LUMINOSIDADE)");
    } else {
      Serial.println(" (luminosidade normal)");
    }
  }

  // Handle SOS Interrupt flag
  if (sosAtivado) {
    sosAtivado = false;
    estadoAtual = EMERGENCIA;
    inicioEmergenciaMs = agora;
    ledApagar();
    ledVermelho();
    Serial.println("[SOS] *** EMERGENCIA ATIVADA! LED VERMELHO por 3s ***");
  }

  switch (estadoAtual) {
    case EMERGENCIA:
      if (agora - inicioEmergenciaMs >= DURACAO_EMERGENCIA) {
        ledApagar();
        estadoAtual = NORMAL;
        Serial.println("[SOS] Emergência encerrada. Retornando ao modo normal.");
      }
      break;

    case NOTURNO:
      if (leituraLDR <= LIMIAR_BAIXA_LUZ) {
        ledApagar();
        estadoAtual = NORMAL;
        Serial.println("[MODO] Luminosidade normalizada. Saindo do modo noturno.");
      } else {
        if (agora - ultimoPiscaMs >= INTERVALO_PISCA) {
          ultimoPiscaMs = agora;
          if (ledAmareloLigado) {
            ledApagar();
          } else {
            ledAmarelo();
            ledAmareloLigado = true;
          }
        }
      }
      break;

    case NORMAL:
      if (leituraLDR > LIMIAR_BAIXA_LUZ) {
        estadoAtual = NOTURNO;
        ultimoPiscaMs = agora;
        ledAmarelo();
        ledAmareloLigado = true;
        Serial.println("[MODO] Baixa luminosidade detectada. Entrando no modo noturno.");
      }
      break;
  }

  server.handleClient();
}
