const int  SERIAL_BAUD_RATE   = 115200;
const int  STARTUP_DELAY_MS   = 2000;
const int  RESULT_DISPLAY_MS  = 1000;
const int  BITS               =  4;
const int  MAX_SIGNED_VALUE   =  7;
const int  MIN_SIGNED_VALUE   = -7;
const char OP_SUBTRACT        = '0';
const char OP_ADD             = '1';
const int  LED_PINS[]         = {7, 6, 5, 4};

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  for (int i = 0; i < BITS; i++) {
    pinMode(LED_PINS[i], OUTPUT);
    digitalWrite(LED_PINS[i], LOW);
  }
  delay(STARTUP_DELAY_MS);
}

void loop() {
  char   operation;
  String inputA, inputB;

  if (!promptOperation(operation))       return;
  if (!promptBinaryOperand("A", inputA)) return;
  if (!promptBinaryOperand("B", inputB)) return;

  int signedA = onesComplementDecode(binaryStringToUint8(inputA));
  int signedB = onesComplementDecode(binaryStringToUint8(inputB));

  performAndPrintResult(operation, signedA, signedB);

  delay(RESULT_DISPLAY_MS);
}

bool promptOperation(char &out) {
  Serial.print("\nOperation — Subtraction (0) or Addition (1) : ");
  String input = readLineFromSerial();
  Serial.println(input);

  if (input.length() != 1 || (input[0] != OP_SUBTRACT && input[0] != OP_ADD)) {
    Serial.println("Invalid. Enter 0 (subtraction) or 1 (addition).");
    return false;
  }

  out = input[0];
  return true;
}

bool promptBinaryOperand(const char* name, String &out) {
  Serial.print("Enter operand ");
  Serial.print(name);
  Serial.print(" (4-bit binary, e.g. 1010): ");

  out = readLineFromSerial();
  Serial.println(out);

  if (!isValid4BitBinary(out)) {
    Serial.println("Invalid. Enter exactly 4 bits using only 0s and 1s.");
    return false;
  }

  return true;
}

void performAndPrintResult(char operation, int signedA, int signedB) {
  int resultDecimal;

  if (operation == OP_SUBTRACT) {
    resultDecimal = signedA - signedB;
    Serial.print("A - B = ");
  } else {
    resultDecimal = signedA + signedB;
    Serial.print("A + B = ");
  }

  if (resultDecimal < MIN_SIGNED_VALUE || resultDecimal > MAX_SIGNED_VALUE) {
    Serial.println("  ⚠ Overflow/underflow — result exceeds 4-bit one's complement range.");
  }

  uint8_t resultEncoded = onesComplementEncode(resultDecimal);

  printUint8AsBinary(resultEncoded, BITS);
  Serial.print("(decimal: ");
  Serial.print(resultDecimal);
  Serial.println(")");

  displayResultOnLEDs(resultEncoded);
}

void displayResultOnLEDs(uint8_t value) {
  for (int i = 0; i < BITS; i++) {
    int bit = (value >> i) & 1;
    digitalWrite(LED_PINS[i], bit ? HIGH : LOW);
  }
}

int onesComplementDecode(uint8_t raw) {
  const uint8_t SIGN_BIT_MASK  = 0b1000;
  const uint8_t MAGNITUDE_MASK = 0b1111;

  if (raw & SIGN_BIT_MASK) {
    return -(~raw & MAGNITUDE_MASK);
  }
  return raw;
}

uint8_t onesComplementEncode(int value) {
  const uint8_t MASK = 0b1111;

  if (value < 0) {
    return (~(-value)) & MASK;
  }
  return value & MASK;
}

bool isValid4BitBinary(const String &s) {
  if (s.length() != BITS) return false;

  for (int i = 0; i < BITS; i++) {
    if (s[i] != '0' && s[i] != '1') return false;
  }
  return true;
}

uint8_t binaryStringToUint8(const String &s) {
  uint8_t value = 0;
  for (int i = 0; i < BITS; i++) {
    value = (value << 1) | (s[i] == '1' ? 1 : 0);
  }
  return value;
}

String readLineFromSerial() {
  while (Serial.available() == 0) {}
  String line = Serial.readStringUntil('\n');
  line.trim();
  return line;
}

void printUint8AsBinary(uint8_t value, int numBits) {
  for (int bit = numBits - 1; bit >= 0; bit--) {
    Serial.print((value >> bit) & 1);
  }
  Serial.println();
}