#!/usr/bin/env python3
"""
Degrau 3: Teste Unitário do Display LCD I2C
Verifica o endereçamento (0x27) e o envio de texto simples.
"""
import lgpio
import time

LCD_I2C_ADDR = 0x27
BACKLIGHT = 0x08
ENABLE = 0x04
RS_DATA = 0x01
RS_CMD = 0x00

def lcd_byte(i2c_handle, data, mode):
    # Envia os 4 bits superiores
    high_nibble = (data & 0xF0) | mode | BACKLIGHT
    lgpio.i2c_write_byte(i2c_handle, high_nibble | ENABLE)
    time.sleep(0.0005)
    lgpio.i2c_write_byte(i2c_handle, high_nibble & ~ENABLE)
    
    # Envia os 4 bits inferiores
    low_nibble = ((data << 4) & 0xF0) | mode | BACKLIGHT
    lgpio.i2c_write_byte(i2c_handle, low_nibble | ENABLE)
    time.sleep(0.0005)
    lgpio.i2c_write_byte(i2c_handle, low_nibble & ~ENABLE)

def main():
    print("--- Teste do Display LCD (I2C) ---")
    
    try:
        h = lgpio.i2c_open(1, LCD_I2C_ADDR)
        print("Módulo I2C encontrado!")
        
        # Sequência básica de inicialização em 4 bits
        time.sleep(0.05)
        for _ in range(3):
            lgpio.i2c_write_byte(h, 0x30 | ENABLE | BACKLIGHT)
            time.sleep(0.0005)
            lgpio.i2c_write_byte(h, 0x30 | BACKLIGHT)
            time.sleep(0.005)
            
        lgpio.i2c_write_byte(h, 0x20 | ENABLE | BACKLIGHT)
        time.sleep(0.0005)
        lgpio.i2c_write_byte(h, 0x20 | BACKLIGHT)
        time.sleep(0.005)
        
        lcd_byte(h, 0x28, RS_CMD) # 4 bit mode, 2 lines
        lcd_byte(h, 0x0C, RS_CMD) # Display On, Cursor Off
        lcd_byte(h, 0x01, RS_CMD) # Clear
        time.sleep(0.002)
        
        # Envia Hello World
        print("Exibindo 'Hello World'...")
        for char in "Hello World!":
            lcd_byte(h, ord(char), RS_DATA)
            
        lcd_byte(h, 0xC0, RS_CMD) # Segunda linha
        for char in "Teste I2C OK":
            lcd_byte(h, ord(char), RS_DATA)
            
        print("Pressione CTRL+C para limpar a tela e sair.")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nEncerrando teste.")
        lcd_byte(h, 0x01, RS_CMD)
    except Exception as e:
        print(f"Erro no I2C: Verifique se o i2cdetect -y 1 mostra 0x27. ({e})")
    finally:
        try:
            lgpio.i2c_close(h)
        except:
            pass

if __name__ == '__main__':
    main()
