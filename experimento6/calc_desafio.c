#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <linux/i2c-dev.h>
#include <wiringPi.h>

// =========================================================================
// 1. DRIVER I2C DE BAIXO NÍVEL (DISPLAY LCD 16x2)
// =========================================================================
#define I2C_BUS "/dev/i2c-1"
#define LCD_ADDR 0x27
#define LCD_CHR  1 // Envio de Dados
#define LCD_CMD  0 // Envio de Comando

int i2c_fd;

void lcd_escrever_byte(uint8_t bits, uint8_t modo) {
    uint8_t byte_alto = modo | (bits & 0xF0) | 0x08; // 0x08 = Backlight ON
    uint8_t byte_baixo = modo | ((bits << 4) & 0xF0) | 0x08;
    
    uint8_t buffer[4] = {
        (uint8_t)(byte_alto | 0x04), (uint8_t)(byte_alto & ~0x04),
        (uint8_t)(byte_baixo | 0x04), (uint8_t)(byte_baixo & ~0x04)
    };
    
    write(i2c_fd, buffer, 4);
    usleep(3000); // Aguarda o display processar
}

void lcd_inicializar() {
    i2c_fd = open(I2C_BUS, O_RDWR);
    if (i2c_fd < 0 || ioctl(i2c_fd, I2C_SLAVE, LCD_ADDR) < 0) {
        printf("[ERRO] Barramento I2C nao encontrado.\n");
        exit(1);
    }
    lcd_escrever_byte(0x33, LCD_CMD);
    lcd_escrever_byte(0x32, LCD_CMD);
    lcd_escrever_byte(0x28, LCD_CMD); // 4 bits, 2 linhas
    lcd_escrever_byte(0x0C, LCD_CMD); // Display ON
    lcd_escrever_byte(0x01, LCD_CMD); // Limpar
}

void lcd_imprimir(const char *str) {
    while (*str) lcd_escrever_byte(*str++, LCD_CHR);
}

void lcd_limpar() {
    lcd_escrever_byte(0x01, LCD_CMD);
    usleep(3000);
}

// =========================================================================
// 2. MULTIPLEXAÇÃO GPIO (TECLADO MATRICIAL 4x4)
// =========================================================================
// Pinos BCM do Raspberry Pi atualizados conforme a bancada
int pinos_linhas[4] = {16, 20, 21, 26};
int pinos_colunas[4] = {19, 13, 6, 5};

char mapa_teclas[4][4] = {
    {'1', '2', '3', '+'},
    {'4', '5', '6', '-'},
    {'7', '8', '9', '*'},
    {'!', '0', '=', '/'} // O '=' funcionará como o "Enter" da calculadora
};

void teclado_inicializar() {
    wiringPiSetupGpio(); // Inicializa usando a numeração BCM
    for (int i = 0; i < 4; i++) {
        pinMode(pinos_linhas[i], OUTPUT);
        digitalWrite(pinos_linhas[i], LOW);
        pinMode(pinos_colunas[i], INPUT);
        pullUpDnControl(pinos_colunas[i], PUD_DOWN); // Resistência Pull-Down ativada
    }
}

char ler_teclado_matricial() {
    for (int l = 0; l < 4; l++) {
        digitalWrite(pinos_linhas[l], HIGH); // Energiza a linha
        for (int c = 0; c < 4; c++) {
            if (digitalRead(pinos_colunas[c]) == HIGH) { // Lê a coluna
                digitalWrite(pinos_linhas[l], LOW); // Desliga a linha antes de retornar
                return mapa_teclas[l][c];
            }
        }
        digitalWrite(pinos_linhas[l], LOW); // Desliga a linha
    }
    return '\0';
}

// =========================================================================
// 3. NÚCLEO DA ULA (CONVERSÕES E CÁLCULOS)
// =========================================================================
#define MAX_4BIT 15

int bin_ascii_para_int(const char *str) {
    if (strlen(str) == 0 || strlen(str) > 4) return -1;
    int res = 0;
    for (int i = 0; i < strlen(str); i++) {
        if (str[i] == '1') res = (res << 1) | 1;
        else if (str[i] == '0') res = (res << 1);
        else return -1;
    }
    return res;
}

void int_para_bin_ascii(int32_t val, char *buf, int bits) {
    uint32_t temp = (uint32_t)val;
    buf[bits] = '\0';
    for (int i = bits - 1; i >= 0; i--) {
        buf[i] = (temp & 1) ? '1' : '0';
        temp >>= 1;
    }
}

// =========================================================================
// 4. LÓGICA PRINCIPAL (PARSER E EXECUÇÃO)
// =========================================================================
int main() {
    printf("Iniciando ULA Standalone (LCD + Keypad)...\n");
    printf("Pinos Linhas: 16, 20, 21, 25 | Colunas: 19, 13, 6, 5\n");
    
    lcd_inicializar();
    teclado_inicializar();
    
    lcd_limpar();
    lcd_imprimir("ULA 4-Bit ARM");
    usleep(2000000);
    lcd_limpar();

    char buffer_entrada[16] = "";
    int pos = 0;
    char tecla_anterior = '\0';

    while (1) {
        char tecla = ler_teclado_matricial();
        
        // Debounce rudimentar
        if (tecla != '\0' && tecla != tecla_anterior) {
            
            if (tecla == '=') {
                // Processamento da expressão (Ex: "1111+0010")
                char bin1_str[10] = "", bin2_str[10] = "";
                char op = '\0';
                int op_idx = -1;

                // 1. Procurar o operador
                for (int i = 0; i < pos; i++) {
                    if (buffer_entrada[i] == '+' || buffer_entrada[i] == '-' || 
                        buffer_entrada[i] == '*' || buffer_entrada[i] == '/' || buffer_entrada[i] == '!') {
                        op = buffer_entrada[i];
                        op_idx = i;
                        break;
                    }
                }

                lcd_limpar(); // Limpa ecrã para os resultados

                if (op_idx != -1) {
                    strncpy(bin1_str, buffer_entrada, op_idx);
                    strcpy(bin2_str, buffer_entrada + op_idx + 1);

                    int val1 = bin_ascii_para_int(bin1_str);
                    int val2 = bin_ascii_para_int(bin2_str);

                    if (val1 == -1 || val1 > MAX_4BIT || (op != '!' && (val2 == -1 || val2 > MAX_4BIT))) {
                        lcd_imprimir("Erro: Limite 4b");
                    } else {
                        char res_str[32];
                        char bin_out[10];

                        switch (op) {
                            case '+':
                                int_para_bin_ascii(val1 + val2, bin_out, 8);
                                sprintf(res_str, "Res: %s", bin_out);
                                lcd_imprimir(res_str);
                                break;
                            case '-':
                                int_para_bin_ascii(val1 - val2, bin_out, 8);
                                if (val1 - val2 < 0) lcd_imprimir("FLAG NEG: ATIVA");
                                else {
                                    sprintf(res_str, "Res: %s", bin_out);
                                    lcd_imprimir(res_str);
                                }
                                break;
                            case '*':
                                { // Multiplicação por Shift e Add
                                    uint32_t res = 0, m1 = val1, m2 = val2;
                                    while (m2 > 0) {
                                        if (m2 & 1) res += m1;
                                        m1 <<= 1; m2 >>= 1;
                                    }
                                    int_para_bin_ascii(res, bin_out, 8);
                                    sprintf(res_str, "Res: %s", bin_out);
                                    lcd_imprimir(res_str);
                                }
                                break;
                            case '/':
                                if (val2 == 0) lcd_imprimir("Erro: Div por 0");
                                else {
                                    sprintf(res_str, "Res: %.2f", (float)val1 / val2);
                                    lcd_imprimir(res_str);
                                }
                                break;
                            case '!':
                                { // Fatorial ARM 64-bit
                                    uint64_t fat = 1;
                                    for (uint8_t i = 1; i <= val1; i++) fat *= i;
                                    sprintf(res_str, "Fat: %llu", fat);
                                    lcd_imprimir(res_str);
                                }
                                break;
                        }
                    }
                } else {
                    lcd_imprimir("Sintaxe Invalida");
                }
                
                // Reinicia para o próximo cálculo
                usleep(4000000); // Mostra o resultado por 4 segundos
                pos = 0;
                memset(buffer_entrada, 0, sizeof(buffer_entrada));
                lcd_limpar();

            } else {
                // Adiciona ao buffer e mostra no LCD
                if (pos < 15) {
                    buffer_entrada[pos++] = tecla;
                    buffer_entrada[pos] = '\0';
                    lcd_limpar();
                    lcd_imprimir(buffer_entrada);
                }
            }
        }
        tecla_anterior = tecla;
        usleep(50000); // Debounce de 50ms (Polling)
    }
    return 0;
}