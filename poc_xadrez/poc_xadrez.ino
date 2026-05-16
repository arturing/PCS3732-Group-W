#include <string.h>
#define LINE_PIN_START 6
#define COLUMN_PIN_START 2
#define NUMBER_LINES 8
#define NUMBER_COLUMNS 4

void setup()
{

  Serial.begin(115200);

  for (int columns = 0; columns < NUMBER_COLUMNS; columns++)
  {
    pinMode(columns+COLUMN_PIN_START, INPUT_PULLUP);
  }
}

bool matrix_prev[NUMBER_LINES][NUMBER_COLUMNS];
bool matrix[NUMBER_LINES][NUMBER_COLUMNS];

void loop()
{

  for (int line = 0; line < NUMBER_LINES; line++)
  {
    int line_pin = line + LINE_PIN_START;
    pinMode(line_pin, OUTPUT);
    digitalWrite(line_pin, LOW);
	
    for (int column = 0; column < NUMBER_COLUMNS; column++){
    	matrix[line][column] = !digitalRead(column+COLUMN_PIN_START);
    }


    pinMode(line_pin, INPUT);
  }

  int diff = memcmp(matrix, matrix_prev, sizeof(matrix));

  if (diff != 0)
  {
    for (int i = 0; i < NUMBER_LINES; i++)
    {
      for (int j= 0; j < NUMBER_COLUMNS; j++){
        if (matrix[i][j] != matrix_prev[i][j])
        {
          Serial.print("Button index ");
          Serial.print(i);
          Serial.print(",");
          Serial.print(j);
          Serial.println(" changed state.");
        }
      }
    }
    memcpy(matrix_prev, matrix, sizeof(matrix));
  }

  delay(10);
}
