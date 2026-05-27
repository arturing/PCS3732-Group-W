#include <WiFi.h>
#include <WebServer.h>
#include <LittleFS.h>
#include "secrets.h" 

#define TRACE(...) Serial.printf(__VA_ARGS__)


WebServer server(80);

void handleSetValues() {
  if (server.hasArg("valA") && server.hasArg("valB") && server.hasArg("sum") && server.hasArg("comp")) {
    int value_a = server.arg("valA").toInt() & 0x0F; 
    int value_b = server.arg("valB").toInt() & 0x0F;

    int result = 0;

    bool isSum = (server.arg("sum").toInt());

    Serial.printf("Received! A: %d | B: %d\n", value_a, value_b);

    value_a = ((value_a > 7) ? value_a - 16 : value_a);
    value_b = ((value_b > 7) ? value_b - 16 : value_b) * (isSum ? 1 : -1);

    result = (value_a + value_b) & 0x0F;

    char binResult[5];
    sprintf(binResult, "%d%d%d%d", 
            (result >> 3) & 1, 
            (result >> 2) & 1, 
            (result >> 1) & 1, 
            result & 1);

    String jsonResponse = "{\"status\":\"success\", \"result\":\"" + String(binResult) + "\"}";
    server.send(200, "application/json", jsonResponse);
  } else {
    server.send(400, "application/json", "{\"status\":\"error\"}");
  }
}
void setup() {
  Serial.begin(115200);
  delay(1000);

  if (!LittleFS.begin(true)) {
    Serial.println("Erro ao montar LittleFS!");
    return;
  }

  WiFi.softAP(ssid, passPhrase);
  Serial.print("Rede criada! IP para acesso: ");
  Serial.println(WiFi.softAPIP()); 
  
  server.on("/api/set-values", HTTP_POST, handleSetValues);

  server.serveStatic("/", LittleFS, "/"); 
  
  server.on("/", HTTP_GET, [](){
    server.sendHeader("Location", "/index.htm", true);
    server.send(302, "text/plain", "");
  });

  server.begin();
  Serial.println("Servidor Web rodando!");
}

void loop() {
  server.handleClient();
}