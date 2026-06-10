#include <WiFi.h>
#include <WebServer.h>
#include <ESP32Servo.h> 

const char* ssid = "toner";
const char* password = "toner123"; 

WebServer server(80);
Servo meuServo;

const int PIN_LED = 7;   
const int PIN_SERVO = 8; 

int ledFreq = 5000;           
int ledResolution = 8;       


bool applyLedcConfig(int freq) {
  ledcDetach(PIN_LED);

  for (int res = 8; res >= 1; res--) {
    if (ledcAttach(PIN_LED, freq, res)) { ledResolution = res; return true; }
  }
  for (int res = 9; res <= 14; res++) {
    if (ledcAttach(PIN_LED, freq, res)) { ledResolution = res; return true; }
  }
  return false;
}

void handleRoot() {
  Serial.println("\n[WEB] Usuário acessou a página principal (/)");
  String html = "<!DOCTYPE html><html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'>";
  html += "<title>ESP32-C3 Control Dashboard</title>";
  html += "<style>body{font-family:Arial,sans-serif; text-align:center; padding:20px; background:#f4f4f4;}";
  html += ".slider {width: 80%; max-width: 400px; margin: 20px auto;} h1{color:#333;}</style></head><body>";
  html += "<h1>ESP32-C3 Control Dashboard</h1>";
  
  html += "<div><h3>Slider 1: Intensidade do LED</h3>";
  html += "<input type='range' min='0' max='255' class='slider' id='ledSlider' onchange='updateLED(this.value)'></div>";
  
  html += "<div><h3>Slider 2: Posicao do Servo (0 a 180)</h3>";
  html += "<input type='range' min='0' max='180' class='slider' id='servoSlider' onchange='updateServo(this.value)'></div>";
  
  html += "<div><h3>Frequencia PWM do LED (Hz)</h3>";
  html += "<input type='number' min='1' max='40000' value='" + String(ledFreq) + "' id='freqInput' style='width:100px; padding:5px; font-size:16px;'> ";
  html += "<button onclick='updateFreq()' style='padding:5px 15px; font-size:16px;'>Aplicar</button></div>";
  
  html += "<script>function updateLED(val) { fetch('/setLED?value=' + val); }";
  html += "function updateServo(val) { fetch('/setServo?value=' + val); }";
  html += "function updateFreq() { var val = document.getElementById('freqInput').value; fetch('/setFreq?value=' + val); }</script>";
  html += "</body></html>";
  
  server.send(200, "text/html", html);
}

void handleLED() {
  if (server.hasArg("value")) {
    int brightness = server.arg("value").toInt();

    int maxDuty = (1 << ledResolution) - 1;
    int scaledBrightness = map(brightness, 0, 255, 0, maxDuty);
    ledcWrite(PIN_LED, scaledBrightness); 
    server.send(200, "text/plain", "OK");
  } else {
    server.send(400, "text/plain", "Bad Request");
  }
}

void handleFreq() {
  Serial.println("\n[REQUISIÇÃO] Rota /setFreq foi chamada!");
  if (server.hasArg("value")) {
    int freq = server.arg("value").toInt();
    if (freq >= 1 && freq <= 40000) {
      ledFreq = freq;
      if (applyLedcConfig(ledFreq)) {
        Serial.print("  -> Frequencia do LED alterada para: "); Serial.print(ledFreq); Serial.print(" Hz (resolucao: "); Serial.print(ledResolution); Serial.println(" bits)");
        server.send(200, "text/plain", "OK");
      } else {
        Serial.println("  [ERRO] Nenhuma resolucao valida para esta frequencia!");
        server.send(400, "text/plain", "Frequencia nao suportada pelo hardware");
      }
    } else {
      Serial.println("  [AVISO] Frequencia fora do intervalo (1-40000)");
      server.send(400, "text/plain", "Frequencia Invalida");
    }
  } else {
    server.send(400, "text/plain", "Bad Request - Missing Value");
  }
}


void handleServo() {
  Serial.println("\n[REQUISIÇÃO] Rota /setServo foi chamada!");

  if (server.hasArg("value")) {
    String rawValue = server.arg("value");
    int angle = rawValue.toInt();
    
    Serial.print("  -> Texto recebido da Web: \""); Serial.print(rawValue); Serial.println("\"");
    Serial.print("  -> Convertido para Inteiro: "); Serial.println(angle);

    if (angle >= 0 && angle <= 180) {
      Serial.print("  -> Enviando comando write("); Serial.print(angle); Serial.println(") para o objeto Servo...");
      
      meuServo.write(angle);
      delay(15); 
      
      Serial.println("  -> Comando enviado com sucesso.");
      server.send(200, "text/plain", "OK");
    } else {
      Serial.print("  [AVISO] Ângulo fora do escopo permitido (0-180): "); Serial.println(angle);
      server.send(400, "text/plain", "Angulo Invalido");
    }

  } else {
    Serial.println("  [ERRO] A requisição chegou, mas falta o argumento '?value=' na URL!");
    server.send(400, "text/plain", "Bad Request - Missing Value");
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000); 
  Serial.println("\n=============================================");
  Serial.println("--- BOOT: INICIANDO DIAGNÓSTICO DO ESP32-C3 ---");
  Serial.println("=============================================");

  Serial.print("[SETUP] Configurando LED no Pino "); Serial.print(PIN_LED); 
  if (applyLedcConfig(ledFreq)) {
    Serial.print(" -> OK (resolucao: "); Serial.print(ledResolution); Serial.println(" bits)");
  } else {
    Serial.println(" -> FALHA ao configurar LEDC!");
  }

  Serial.println("[SETUP] Alocando Timers de hardware para o PWM...");
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);

  Serial.print("[SETUP] Configurando Servo no Pino "); Serial.println(PIN_SERVO);
  meuServo.setPeriodHertz(50); 
  
  int canalAlocado = meuServo.attach(PIN_SERVO, 500, 2500); 
  Serial.print("  -> Canal PWM atribuído ao servo: "); Serial.println(canalAlocado);

  Serial.print("[REDE] Criando Hotspot: "); Serial.println(ssid);
  WiFi.softAP(ssid, password);

  IPAddress IP = WiFi.softAPIP();
  Serial.print("[REDE] Hotspot Pronto. IP do Dashboard: "); Serial.println(IP);

  server.on("/", HTTP_GET, handleRoot);
  server.on("/setLED", HTTP_GET, handleLED);
  server.on("/setServo", HTTP_GET, handleServo);
  server.on("/setFreq", HTTP_GET, handleFreq);
  
  server.begin();
  Serial.println("[SISTEMA] Servidor HTTP Online e aguardando comandos...\n");
}

void loop() {
  server.handleClient();
   
}