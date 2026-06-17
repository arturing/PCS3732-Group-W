#include <WiFi.h>
#include <WebServer.h>

const char* ssid     = "toner";
const char* password = "toner123";

WebServer server(80);

const int PIN_LDR = 36;
const int PIN_BOTAO_PEDESTRE = 26;

const int PIN_LED_R = 32;
const int PIN_LED_G = 33;
const int PIN_LED_B = 25;

const int LIMIAR_BAIXA_LUZ = 2000;

const unsigned long TEMPO_VERDE    = 5000;
const unsigned long TEMPO_AMARELO  = 2000;
const unsigned long TEMPO_VERMELHO = 5000;
const unsigned long NOTURNO_SEMI_PERIODO = 500;
const unsigned long TEMPO_TRAVESSIA = 5000;
const unsigned long INTERVALO_LDR = 1000;

volatile int leituraLDR = 0;
unsigned long ultimaLeituraMs = 0;

// Interrupt debounce flag and timer
volatile bool pedestreSolicitado = false;
volatile unsigned long ultimoDebounceMs = 0;
const unsigned long JANELA_DEBOUNCE = 200;

enum EstadoSemaforo {
  VERDE,
  AMARELO,
  VERMELHO,
  NOTURNO,
  PEDESTRE_TRANSICAO,
  PEDESTRE_VERMELHO
};

EstadoSemaforo estadoAtual    = VERDE;
EstadoSemaforo estadoAnterior = VERDE;

unsigned long inicioEstadoMs  = 0;
unsigned long ultimoPiscaMs   = 0;
bool piscaLigado              = false;
bool travessiaEmAndamento     = false;

// Pedestrian Button ISR (Hardware interrupt on FALLING edge)
void IRAM_ATTR isrBotaoPedestre() {
  unsigned long agora = millis();
  // Software debounce
  if (agora - ultimoDebounceMs >= JANELA_DEBOUNCE) {
    pedestreSolicitado = true;
    ultimoDebounceMs = agora;
  }
}

void ledApagar() {
  digitalWrite(PIN_LED_R, LOW);
  digitalWrite(PIN_LED_G, LOW);
  digitalWrite(PIN_LED_B, LOW);
}

void ledVerde() {
  digitalWrite(PIN_LED_R, LOW);
  digitalWrite(PIN_LED_G, HIGH);
  digitalWrite(PIN_LED_B, LOW);
}

void ledAmarelo() {
  digitalWrite(PIN_LED_R, HIGH);
  digitalWrite(PIN_LED_G, HIGH);
  digitalWrite(PIN_LED_B, LOW);
}

void ledVermelho() {
  digitalWrite(PIN_LED_R, HIGH);
  digitalWrite(PIN_LED_G, LOW);
  digitalWrite(PIN_LED_B, LOW);
}

void transitarPara(EstadoSemaforo novoEstado) {
  estadoAtual = novoEstado;
  inicioEstadoMs = millis();

  switch (novoEstado) {
    case VERDE:
      ledVerde();
      travessiaEmAndamento = false;
      Serial.println("[SEMAFORO] -> VERDE");
      break;
    case AMARELO:
      ledAmarelo();
      Serial.println("[SEMAFORO] -> AMARELO");
      break;
    case VERMELHO:
      ledVermelho();
      Serial.println("[SEMAFORO] -> VERMELHO");
      break;
    case NOTURNO:
      ledAmarelo();
      piscaLigado = true;
      ultimoPiscaMs = millis();
      Serial.println("[SEMAFORO] -> MODO NOTURNO (pisca amarelo 1Hz)");
      break;
    case PEDESTRE_TRANSICAO:
      ledAmarelo();
      travessiaEmAndamento = true;
      Serial.println("[PEDESTRE] -> Transição segura (amarelo)");
      break;
    case PEDESTRE_VERMELHO:
      ledVermelho();
      Serial.println("[PEDESTRE] -> Travessia liberada (vermelho para veículos)");
      break;
  }
}

void handleRoot() {
  Serial.println("\n[WEB] Usuário acessou a página principal (/)");

  String html = "<!DOCTYPE html><html><head>";
  html += "<meta charset='UTF-8'>";
  html += "<meta name='viewport' content='width=device-width, initial-scale=1.0'>";
  html += "<title>ESP32 - Semáforo Inteligente</title>";
  html += "<style>";
  html += "* { box-sizing: border-box; margin: 0; padding: 0; }";
  html += "body { font-family: 'Segoe UI', Arial, sans-serif; background: #1a1a2e; color: #e0e0e0; min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 30px 15px; }";
  html += "h1 { color: #00d4ff; font-size: 1.5em; margin-bottom: 25px; text-shadow: 0 0 10px rgba(0,212,255,0.3); }";
  html += ".card { background: #16213e; border-radius: 16px; padding: 25px; margin: 10px 0; width: 90%; max-width: 420px; box-shadow: 0 4px 20px rgba(0,0,0,0.4); border: 1px solid #0f3460; }";
  html += ".card h2 { font-size: 1em; color: #a0a0d0; margin-bottom: 15px; }";
  html += ".semaforo { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 15px; background: #111; border-radius: 12px; width: 80px; margin: 0 auto 15px; }";
  html += ".luz { width: 50px; height: 50px; border-radius: 50%; border: 2px solid #333; transition: all 0.4s ease; }";
  html += ".luz.off { background: #222; }";
  html += ".luz.vermelho { background: #e5383b; box-shadow: 0 0 20px #e5383b; }";
  html += ".luz.amarelo { background: #ffc300; box-shadow: 0 0 20px #ffc300; }";
  html += ".luz.verde { background: #52b788; box-shadow: 0 0 20px #52b788; }";
  html += ".ldr-value { font-size: 2.5em; font-weight: bold; color: #00d4ff; text-align: center; }";
  html += ".ldr-bar { width: 100%; height: 10px; background: #0f3460; border-radius: 5px; margin-top: 10px; overflow: hidden; }";
  html += ".ldr-fill { height: 100%; border-radius: 5px; transition: width 0.5s ease, background 0.5s ease; }";
  html += ".status { text-align: center; font-size: 1.1em; padding: 10px; border-radius: 8px; margin-top: 10px; font-weight: bold; }";
  html += ".status.normal { background: #1b4332; color: #52b788; }";
  html += ".status.noturno { background: #433500; color: #ffc300; animation: pulse 1s infinite; }";
  html += ".status.pedestre { background: #1b3a5c; color: #74b9ff; }";
  html += "@keyframes pulse { 0%,100%{ opacity:1; } 50%{ opacity:0.6; } }";
  html += ".info { font-size: 0.8em; color: #7a7aaa; margin-top: 8px; text-align: center; }";
  html += "</style></head><body>";
  html += "<h1>&#128678; Semáforo Inteligente</h1>";
  html += "<div class='card'>";
  html += "<h2>&#128306; Semáforo</h2>";
  html += "<div class='semaforo'>";
  html += "<div class='luz off' id='luzR'></div>";
  html += "<div class='luz off' id='luzA'></div>";
  html += "<div class='luz off' id='luzV'></div>";
  html += "</div>";
  html += "<div class='status normal' id='sysStatus'>Carregando...</div>";
  html += "</div>";
  html += "<div class='card'>";
  html += "<h2>&#9728;&#65039; Luminosidade (LDR)</h2>";
  html += "<div class='ldr-value' id='ldrVal'>---</div>";
  html += "<div class='ldr-bar'><div class='ldr-fill' id='ldrBar' style='width:0%;background:#00d4ff;'></div></div>";
  html += "<div class='info'>ADC 12 bits (0–4095) | Limiar noturno: " + String(LIMIAR_BAIXA_LUZ) + "</div>";
  html += "</div>";
  html += "<script>";
  html += "function att() {";
  html += "  fetch('/dados').then(r=>r.json()).then(d=>{";
  html += "    document.getElementById('ldrVal').textContent=d.ldr;";
  html += "    var p=(d.ldr/4095*100).toFixed(1);";
  html += "    var b=document.getElementById('ldrBar');";
  html += "    b.style.width=p+'%';";
  html += "    b.style.background=d.ldr>" + String(LIMIAR_BAIXA_LUZ) + "?'#ffc300':'#00d4ff';";
  html += "    var R=document.getElementById('luzR');";
  html += "    var A=document.getElementById('luzA');";
  html += "    var V=document.getElementById('luzV');";
  html += "    R.className='luz '+(d.cor=='vermelho'?'vermelho':'off');";
  html += "    A.className='luz '+(d.cor=='amarelo'?'amarelo':'off');";
  html += "    V.className='luz '+(d.cor=='verde'?'verde':'off');";
  html += "    var st=document.getElementById('sysStatus');";
  html += "    if(d.estado=='NOTURNO'){st.textContent='\\uD83C\\uDF19 Modo Noturno';st.className='status noturno';}";
  html += "    else if(d.estado=='PEDESTRE_TRANSICAO'||d.estado=='PEDESTRE_VERMELHO'){st.textContent='\\uD83D\\uDEB6 Travessia de Pedestres';st.className='status pedestre';}";
  html += "    else{st.textContent='\\u2705 Ciclo Normal ('+d.estado+')';st.className='status normal';}";
  html += "  }).catch(e=>{console.error(e);});";
  html += "}";
  html += "att(); setInterval(att,500);";
  html += "</script>";
  html += "</body></html>";
  server.send(200, "text/html", html);
}

void handleDados() {
  String estado;
  switch (estadoAtual) {
    case VERDE:               estado = "VERDE";               break;
    case AMARELO:             estado = "AMARELO";             break;
    case VERMELHO:            estado = "VERMELHO";            break;
    case NOTURNO:             estado = "NOTURNO";             break;
    case PEDESTRE_TRANSICAO:  estado = "PEDESTRE_TRANSICAO";  break;
    case PEDESTRE_VERMELHO:   estado = "PEDESTRE_VERMELHO";   break;
  }

  String cor = "apagado";
  switch (estadoAtual) {
    case VERDE:              cor = "verde";    break;
    case AMARELO:            cor = "amarelo";  break;
    case VERMELHO:           cor = "vermelho"; break;
    case PEDESTRE_TRANSICAO: cor = "amarelo";  break;
    case PEDESTRE_VERMELHO:  cor = "vermelho"; break;
    case NOTURNO:
      cor = piscaLigado ? "amarelo" : "apagado";
      break;
  }

  String json = "{";
  json += "\"ldr\":" + String(leituraLDR) + ",";
  json += "\"estado\":\"" + estado + "\",";
  json += "\"cor\":\"" + cor + "\"";
  json += "}";

  server.send(200, "application/json", json);
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=============================================");
  Serial.println("--- BOOT: SEMAFORO INTELIGENTE ESP32 ---");
  Serial.println("=============================================");

  pinMode(PIN_LED_R, OUTPUT);
  pinMode(PIN_LED_G, OUTPUT);
  pinMode(PIN_LED_B, OUTPUT);
  ledApagar();
  Serial.println("[SETUP] LED RGB configurado.");

  analogReadResolution(12);
  Serial.print("[SETUP] LDR no pino ADC "); Serial.println(PIN_LDR);

  pinMode(PIN_BOTAO_PEDESTRE, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_BOTAO_PEDESTRE), isrBotaoPedestre, FALLING);
  Serial.print("[SETUP] Botão pedestre no pino ");
  Serial.print(PIN_BOTAO_PEDESTRE);
  Serial.println(" (interrupção FALLING, pull-up interno).");

  Serial.print("[REDE] Criando Hotspot: "); Serial.println(ssid);
  WiFi.softAP(ssid, password);
  IPAddress IP = WiFi.softAPIP();
  Serial.print("[REDE] IP do Dashboard: "); Serial.println(IP);

  server.on("/",      HTTP_GET, handleRoot);
  server.on("/dados", HTTP_GET, handleDados);
  server.begin();
  Serial.println("[SISTEMA] Servidor HTTP Online.\n");

  transitarPara(VERDE);
}

void loop() {
  unsigned long agora = millis();

  // Non-blocking LDR reading
  if (agora - ultimaLeituraMs >= INTERVALO_LDR) {
    ultimaLeituraMs = agora;
    leituraLDR = analogRead(PIN_LDR);
  }

  bool baixaLuz = (leituraLDR > LIMIAR_BAIXA_LUZ);

  if (baixaLuz && estadoAtual != NOTURNO
               && estadoAtual != PEDESTRE_TRANSICAO
               && estadoAtual != PEDESTRE_VERMELHO) {
    estadoAnterior = estadoAtual;
    transitarPara(NOTURNO);
  }

  if (!baixaLuz && estadoAtual == NOTURNO) {
    Serial.println("[MODO] Luminosidade normalizada. Retornando ao ciclo normal.");
    transitarPara(VERDE);
  }

  // Handle pedestrian request flag
  if (pedestreSolicitado) {
    pedestreSolicitado = false;

    if (!travessiaEmAndamento) {
      Serial.println("[PEDESTRE] Solicitação de travessia recebida!");

      switch (estadoAtual) {
        case VERDE:
          transitarPara(PEDESTRE_TRANSICAO);
          break;
        case AMARELO:
          transitarPara(PEDESTRE_VERMELHO);
          break;
        case VERMELHO:
          transitarPara(PEDESTRE_VERMELHO);
          break;
        case NOTURNO:
          Serial.println("[PEDESTRE] Modo noturno ativo. Travessia ignorada.");
          break;
        default:
          break;
      }
    } else {
      Serial.println("[PEDESTRE] Travessia já em andamento, ignorando.");
    }
  }

  unsigned long tempoNoEstado = agora - inicioEstadoMs;

  switch (estadoAtual) {
    case VERDE:
      if (tempoNoEstado >= TEMPO_VERDE) {
        transitarPara(AMARELO);
      }
      break;

    case AMARELO:
      if (tempoNoEstado >= TEMPO_AMARELO) {
        transitarPara(VERMELHO);
      }
      break;

    case VERMELHO:
      if (tempoNoEstado >= TEMPO_VERMELHO) {
        transitarPara(VERDE);
      }
      break;

    case NOTURNO:
      if (agora - ultimoPiscaMs >= NOTURNO_SEMI_PERIODO) {
        ultimoPiscaMs = agora;
        if (piscaLigado) {
          ledApagar();
          piscaLigado = false;
        } else {
          ledAmarelo();
          piscaLigado = true;
        }
      }
      break;

    case PEDESTRE_TRANSICAO:
      if (tempoNoEstado >= TEMPO_AMARELO) {
        transitarPara(PEDESTRE_VERMELHO);
      }
      break;

    case PEDESTRE_VERMELHO:
      if (tempoNoEstado >= TEMPO_TRAVESSIA) {
        Serial.println("[PEDESTRE] Travessia concluída. Retornando ao ciclo.");
        transitarPara(VERDE);
      }
      break;
  }

  server.handleClient();
}
