#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>

// --- FUNÇÕES AUXILIARES DE CONVERSÃO GENÉRICAS ---

// Agora valida o tamanho com base no parâmetro num_bits
int64_t bin_ascii_para_int(const char *str, int num_bits) {
    int64_t resultado = 0;
    int len = strlen(str);
    
    if (len > num_bits) return -1; // Validação dinâmica de tamanho

    for (int i = 0; i < len; i++) {
        if (str[i] == '1') {
            resultado = (resultado << 1) | 1;
        } else if (str[i] == '0') {
            resultado = (resultado << 1);
        } else {
            return -1; 
        }
    }
    return resultado;
}

void int_para_bin_ascii(int64_t valor, char *buffer_saida, int num_bits) {
    uint64_t temp = (uint64_t)valor;
    buffer_saida[num_bits] = '\0';
    for (int i = num_bits - 1; i >= 0; i--) {
        buffer_saida[i] = (temp & 1) ? '1' : '0';
        temp >>= 1;
    }
}

// --- OPERAÇÕES NATIVAS DA ULA (Tipos expandidos para suportar N-bits) ---

int64_t op_add(uint32_t a, uint32_t b) {
    return (int64_t)(a + b);
}

int64_t op_sub(uint32_t a, uint32_t b) {
    return (int64_t)a - (int64_t)b;
}

uint64_t op_mul_shift_add(uint32_t a, uint32_t b) {
    uint64_t resultado = 0;
    uint64_t multiplicando = a;
    uint64_t multiplicador = b;

    while (multiplicador > 0) {
        if (multiplicador & 1) {
            resultado += multiplicando;
        }
        multiplicando <<= 1;
        multiplicador >>= 1;
    }
    return resultado;
}

float op_div(uint32_t a, uint32_t b) {
    if (b == 0) return -1.0f; 
    return (float)a / (float)b;
}

uint64_t op_factorial(uint32_t n) {
    uint64_t fat_64 = 1; 
    for (uint32_t i = 1; i <= n; i++) {
        fat_64 *= i;
    }
    return fat_64;
}

// --- FLUXO PRINCIPAL DA CALCULADORA ---
int main(int argc, char *argv[]) {
    // Parâmetro padrão é 4 bits, mas aceita argumentos de 1 a 32 bits
    int num_bits = 4; 
    if (argc > 1) {
        int argumento = atoi(argv[1]);
        if (argumento >= 1 && argumento <= 32) {
            num_bits = argumento;
        } else {
            printf("[ERRO] Largura de bits invalida (%d). Use entre 1 e 32.\n", argumento);
            return 1;
        }
    }

    // Calcula o valor máximo dinamicamente (Ex: para 4 bits -> 15. Para 8 bits -> 255)
    uint64_t MAX_VAL = (1ULL << num_bits) - 1;

    printf("==================================================\n");
    print(f"   PCS3732 - CALCULADORA CONFIGURADA PARA %d BITS   \n", num_bits);
    printf("==================================================\n");
    printf("Valores aceitos: 0 ate %llu\n", MAX_VAL);

    while (true) {
        char str_num1[40], str_num2[40]; // Buffers expandidos para suportar strings maiores
        char opcode;

        printf("\n>> ");

        int scan_res = scanf("%s %c %s", str_num1, &opcode, str_num2);
        if (scan_res == EOF) break; 
        
        if (scan_res != 3) {
            printf("[AVISO] Formato invalido. Use: [Binario1] [Opcode] [Binario2]\n");
            while (getchar() != '\n'); 
            continue;
        }

        // Passando o parâmetro dinâmico de bits para a conversão
        int64_t val1 = bin_ascii_para_int(str_num1, num_bits);
        int64_t val2 = bin_ascii_para_int(str_num2, num_bits);

        if (val1 == -1 || val2 == -1 || val1 > MAX_VAL || val2 > MAX_VAL) {
            printf("[ERRO] Entrada invalida! Use sequencias de ate %d bits (max: %llu em decimal).\n", num_bits, MAX_VAL);
            continue;
        }

        uint32_t num1 = (uint32_t)val1;
        uint32_t num2 = (uint32_t)val2;
        char resultado_ascii[40];

        struct timespec start, end;
        long elapsed_ns;

        switch (opcode) {
            case '+':
                {
                    clock_gettime(CLOCK_MONOTONIC, &start);
                    int64_t res_add = op_add(num1, num2);
                    clock_gettime(CLOCK_MONOTONIC, &end);
                    
                    int_para_bin_ascii(res_add, resultado_ascii, num_bits); 
                    printf("Resultado Binario: %s | Decimal: %lld\n", resultado_ascii, res_add);
                }
                break;

            case '-':
                {
                    clock_gettime(CLOCK_MONOTONIC, &start);
                    int64_t res_sub = op_sub(num1, num2); 
                    clock_gettime(CLOCK_MONOTONIC, &end);
                    
                    int_para_bin_ascii(res_sub, resultado_ascii, num_bits); 
                    if (res_sub < 0) {
                        printf("Resultado Binario: %s | Decimal: %lld [FLAG SINAL NEGATIVO: ATIVADA]\n", resultado_ascii, res_sub);
                    } else {
                        printf("Resultado Binario: %s | Decimal: %lld [FLAG SINAL NEGATIVO: DESATIVADA]\n", resultado_ascii, res_sub);
                    }
                }
                break;

            case '*':
                {
                    clock_gettime(CLOCK_MONOTONIC, &start);
                    uint64_t res_mul = op_mul_shift_add(num1, num2);
                    clock_gettime(CLOCK_MONOTONIC, &end);
                    
                    int_para_bin_ascii(res_mul, resultado_ascii, num_bits); 
                    printf("Resultado Binario: %s | Decimal: %llu\n", resultado_ascii, res_mul);
                }
                break;

            case '/':
                {
                    clock_gettime(CLOCK_MONOTONIC, &start);
                    float res_div = op_div(num1, num2); 
                    clock_gettime(CLOCK_MONOTONIC, &end);
                    
                    if (num2 == 0) {
                        printf("[AVISO RNF01] Divisao por zero (A/0) detetada!\n");
                    } else {
                        printf("Resultado (Divisao): %.3f\n", res_div);
                    }
                }
                break;

            case '!':
                {
                    clock_gettime(CLOCK_MONOTONIC, &start);
                    uint64_t res_fat = op_factorial(num1); 
                    clock_gettime(CLOCK_MONOTONIC, &end);
                    
                    printf("Resultado Fatorial (!): %llu\n", res_fat);
                    printf("[Analise ARM 64-bit]: Processado de forma nativa (Palavra de 64 bits).\n");
                    if (res_fat > 0xFFFFFFFF) {
                        printf("[Analise RISC-V 32-bit]: GERARIA OVERFLOW! Exigiria multiplas instrucoes.\n");
                    }
                }
                break;

            default:
                printf("[AVISO] Opcode '%c' invalido.\n", opcode);
                continue;
        }

        elapsed_ns = (end.tv_sec - start.tv_sec) * 1000000000L + (end.tv_nsec - start.tv_nsec);
        printf("[BENCHMARK] Tempo: %ld ns\n", elapsed_ns);
    }
    return 0;
}