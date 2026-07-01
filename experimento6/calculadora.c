#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>

// [RF01] Escopo: Valores binários de 4 bits (0 a 15) [cite: 64]
#define MAX_4BIT 15
#define MIN_4BIT 0

// --- FUNÇÕES AUXILIARES DE CONVERSÃO (Exigência da Página 7) ---

// Converte a string binária digitada pelo usuário ("1111") para valor inteiro 
int bin_ascii_para_int(const char *str) {
    int resultado = 0;
    int len = strlen(str);
    
    if (len > 4) return -1; // Garante limite estrito de 4 bits [cite: 64]

    for (int i = 0; i < len; i++) {
        if (str[i] == '1') {
            resultado = (resultado << 1) | 1;
        } else if (str[i] == '0') {
            resultado = (resultado << 1);
        } else {
            return -1; // Caractere inválido detetado
        }
    }
    return resultado;
}

// [Página 7] Bloco: Conversão Binário -> ASCII para envio ao Buffer de Vídeo 
void int_para_bin_ascii(int32_t valor, char *buffer_saida, int num_bits) {
    uint32_t temp = (uint32_t)valor;
    buffer_saida[num_bits] = '\0';
    for (int i = num_bits - 1; i >= 0; i--) {
        buffer_saida[i] = (temp & 1) ? '1' : '0';
        temp >>= 1;
    }
}

// --- OPERAÇÕES NATIVAS DA ULA (Fluxograma da Página 7) ---

// [+] ADD: Instrução direta no pipeline da CPU [cite: 142]
int32_t op_add(uint8_t a, uint8_t b) {
    return (int32_t)(a + b);
}

// [-] SUB: Checagem obrigatória da flag de sinal negativo [cite: 143, 145]
void op_sub(uint8_t a, uint8_t b) {
    int32_t sub_resultado = (int32_t)a - (int32_t)b;
    char ascii_bin[33];
    
    // Converte o valor absoluto ou complemento para exibição de bits [cite: 149, 150]
    int_para_bin_ascii(sub_resultado, ascii_bin, 8); 

    if (sub_resultado < 0) {
        // [Página 7] Ativação obrigatória da flag de sinal negativo [cite: 145]
        printf("Resultado Binario (ASCII): %s | Decimal: %d [FLAG SINAL NEGATIVO: ATIVADA]\n", ascii_bin, sub_resultado);
    } else {
        printf("Resultado Binario (ASCII): %s | Decimal: %d [FLAG SINAL NEGATIVO: DESATIVADA]\n", ascii_bin, sub_resultado);
    }
}

// [*] MUL: Deslocamento de bits (Shift) e adição [cite: 146]
uint32_t op_mul_shift_add(uint8_t a, uint8_t b) {
    uint32_t resultado = 0;
    uint32_t multiplicando = a;
    uint32_t multiplicador = b;

    while (multiplicador > 0) {
        if (multiplicador & 1) {
            resultado += multiplicando;
        }
        multiplicando <<= 1; // Shift Left [cite: 146]
        multiplicador >>= 1; // Shift Right [cite: 146]
    }
    return resultado;
}

// [/] DIV: Tratamento de Exceção (Evita Kernel Panic) 
void op_div(uint8_t a, uint8_t b) {
    if (b == 0) {
        // [RNF01] Sistema exibe aviso, não falha e aguarda novo input 
        printf("[AVISO RNF01] Divisao por zero (A/0) detetada! Operacao abortada para manter estabilidade do Kernel.\n");
        return;
    }
    float res_div = (float)a / (float)b;
    printf("Resultado (Divisao): %.3f\n", res_div);
}

// [!] FAT: Loop iterativo com monitoramento de overflow de bits [cite: 147, 148]
void op_factorial(uint8_t n) {
    uint64_t fat_64 = 1; // Palavra nativa de 64 bits do ARM Cortex-A53 [cite: 46, 123]
    bool overflow_32_bits = false;

    for (uint8_t i = 1; i <= n; i++) {
        fat_64 *= i;
        // [Página 7] Monitoramento de overflow de 32 bits exigido [cite: 148]
        if (fat_64 > 0xFFFFFFFF && !overflow_32_bits) {
            overflow_32_bits = true;
        }
    }

    printf("Resultado Fatorial (!): %llu\n", fat_64);
    printf("[Analise ARM 64-bit]: Processado de forma nativa (Palavra de 64 bits)[cite: 123, 124].\n");
    
    if (overflow_32_bits) {
        // Evidência de Escalabilidade solicitada na Página 5 [cite: 119, 130]
        printf("[Analise RISC-V 32-bit]: GERARIA OVERFLOW! Exigiria multiplas instrucoes encadeadas (Overhead)[cite: 127, 130].\n");
    }
}

// --- FLUXO PRINCIPAL DA CALCULADORA ---
int main() {
    // [RF02] Inicialização do Buffer de Vídeo via HDMI-VGA [cite: 76, 134, 151]
    printf("==================================================\n");
    printf("   PCS3732 - CALCULADORA DE ARQUITETURAS (ARM)    \n");
    printf("==================================================\n");

    // Loop de Execução Contínuo (Garante RNF01: estável e aguardando novo input) 
    while (true) {
        char str_num1[20], str_num2[20];
        char opcode;

        printf("\nIntroduza a operacao em binario (Ex: 1111 + 0010 ou 0101 ! 0000):\n");
        printf(">> ");

        // Leitura de strings para validar a digitação da sequência binária 
        if (scanf("%s %c %s", str_num1, &opcode, str_num2) != 3) {
            printf("[AVISO] Formato invalido. Use: [Binario1] [Opcode] [Binario2]\n");
            while (getchar() != '\n'); // Limpa buffer do teclado [cite: 139]
            continue;
        }

        // Conversão de ASCII (Teclado) para os Registradores Inteiros da ULA [cite: 134, 139]
        int val1 = bin_ascii_para_int(str_num1);
        int val2 = bin_ascii_para_int(str_num2);

        // [RF01] Validação de limites físicos (0 a 15 / 4 bits) 
        if (val1 == -1 || val2 == -1 || val1 > MAX_4BIT || val2 > MAX_4BIT) {
            printf("[ERRO RF01] Entrada invalida! Use sequencias binarias de ate 4 bits (0000 a 1111).\n");
            continue;
        }

        uint8_t num1 = (uint8_t)val1;
        uint8_t num2 = (uint8_t)val2;
        char resultado_ascii[33];

        // Decodificador de OpCode [cite: 144]
        switch (opcode) {
            case '+':
                {
                    int32_t res = op_add(num1, num2);
                    int_para_bin_ascii(res, resultado_ascii, 8); // Conversão Binário -> ASCII [cite: 150]
                    printf("Resultado Binario (ASCII): %s | Decimal: %d\n", resultado_ascii, res);
                }
                break;

            case '-':
                op_sub(num1, num2); // Já faz a validação interna da flag de sinal [cite: 145]
                break;

            case '*':
                {
                    uint32_t res = op_mul_shift_add(num1, num2);
                    int_para_bin_ascii(res, resultado_ascii, 8); // Conversão Binário -> ASCII [cite: 150]
                    printf("Resultado Binario (ASCII): %s | Decimal: %u\n", resultado_ascii, res);
                }
                break;

            case '/':
                op_div(num1, num2); // Tratamento de exceção robusto [cite: 72]
                break;

            case '!':
                op_factorial(num1); // Análise de bits e monitoramento de overflow [cite: 148]
                break;

            default:
                // [RNF01] Mensagem de aviso sem travar o sistema 
                printf("[AVISO RNF01] Opcode '%c' invalido. Sistema aguardando nova instrucao.\n", opcode);
                break;
        }
    }
    return 0;
}