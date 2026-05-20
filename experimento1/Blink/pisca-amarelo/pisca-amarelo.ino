#include <Adafruit_NeoPixel.h>

#define RGB_LED_PIN 8
Adafruit_NeoPixel pixels(1, RGB_LED_PIN, NEO_GRB + NEO_KHZ800);

void setup() {
  Serial.begin(115200);
  pixels.begin();
}

void loop() {
  // Blinking yellow
  pixels.setPixelColor(0, pixels.Color(255, 255, 0));
  pixels.show();
  delay(500);
  pixels.setPixelColor(0, pixels.Color(0, 0, 0));
  pixels.show();
  delay(500);
}
