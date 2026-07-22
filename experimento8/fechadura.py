"""
Experimento 8 — Fechadura Eletrônica
=====================================
Implementação de uma fechadura eletrônica usando Raspberry Pi 3.

Componentes:
  - Teclado Matricial 4x4 (GPIO com varredura de linhas/colunas)
  - Display LCD 16x2 via I2C (endereço 0x27)
  - Sensor Ultrassônico HC-SR04 (GPIO — polling)
  - Buzzer passivo (GPIO digital)

Arquitetura de software: máquina de estados não-bloqueante
  - IDLE: Aguarda entrada do usuário, monitora sensor
  - INPUT: Recebe dígitos da senha, exibe asteriscos no LCD
  - PROCESSING: Compara hash SHA-256 da senha inserida
  - SUCCESS: Acesso autorizado — bipe curto, exibe "Aberto"
  - FAILURE: Acesso negado — bipe longo, incrementa contador
  - COOLDOWN: Bloqueio temporário após múltiplas falhas
  - ALARM: Alerta sonoro/visual quando sensor detecta violação

Segurança:
  - Senhas armazenadas como hash SHA-256 (nunca em texto plano)
  - Bloqueio temporário (cooldown) após 3 tentativas incorretas
  - Detecção de violação física via sensor ultrassônico
"""

import lgpio
import time
import hashlib
import hmac

# ---------------------------------------------------------------------------
# Configuração de Pinos GPIO
# ---------------------------------------------------------------------------

# Teclado Matricial 4x4 — linhas (OUTPUT) e colunas (INPUT com pull-up)
PIN_ROWS = [16, 20, 21, 26]  # R1, R2, R3, R4
PIN_COLS = [19, 13, 6, 5]    # C1, C2, C3, C4

# Display LCD 16x2 via I2C (utiliza /dev/i2c-1)
LCD_I2C_ADDR = 0x27
LCD_COLS = 16
LCD_ROWS = 2

# Sensor Ultrassônico HC-SR04
PIN_TRIG = 14
PIN_ECHO = 15

# Buzzer
PIN_BUZZER = 12

# Mapeamento do teclado matricial 4x4
KEYPAD_MAP = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D'],
]
# Teclas especiais:
#   '#' = Confirmar (Submit)
#   '*' = Apagar último dígito (Backspace)
#   'A'..'D' = Reservadas (não utilizadas na senha)

# ---------------------------------------------------------------------------
# Configuração da Fechadura
# ---------------------------------------------------------------------------

# Senha padrão: "1234" — armazenada como hash SHA-256
DEFAULT_PASSWORD_HASH = hashlib.sha256("1234".encode()).hexdigest()

MAX_PASSWORD_LENGTH = 6
MIN_PASSWORD_LENGTH = 4
MAX_FAILED_ATTEMPTS = 3
COOLDOWN_SECONDS = 30

# Limiar de distância para considerar a porta "fechada" (em cm)
# Se a distância medida for MENOR que este valor -> porta fechada
# Se MAIOR -> porta aberta (possível violação)
DOOR_CLOSED_THRESHOLD_CM = 10.0

# Intervalo de polling do sensor (segundos)
SENSOR_POLL_INTERVAL = 0.5

# Debounce do teclado (segundos)
KEY_DEBOUNCE_TIME = 0.05

# Tempo de exibição de mensagens temporárias no LCD (segundos)
MESSAGE_DISPLAY_TIME = 3.0

# Buzzer — durações em milissegundos
BUZZ_SHORT_MS = 150    # Bipe curto (sucesso)
BUZZ_LONG_MS = 800     # Bipe longo (falha)
BUZZ_ALARM_MS = 200    # Bipe de alarme (repetido)


# ---------------------------------------------------------------------------
# Classe LCD I2C (compatível com PCF8574 backpack)
# ---------------------------------------------------------------------------

class LcdI2C:
    """
    Driver para display LCD 16x2 com módulo I2C PCF8574.
    Utiliza o barramento I2C via lgpio (i2c_open/i2c_write_byte).

    O PCF8574 expõe 8 bits que controlam o LCD no modo 4 bits:
      P0 = RS  (Register Select)
      P1 = RW  (Read/Write, sempre 0 para escrita)
      P2 = EN  (Enable)
      P3 = Backlight
      P4..P7 = D4..D7 (dados em modo 4 bits)
    """

    BACKLIGHT = 0x08
    ENABLE = 0x04
    RS_DATA = 0x01
    RS_CMD = 0x00

    # Comandos do HD44780
    CMD_CLEAR = 0x01
    CMD_HOME = 0x02
    CMD_ENTRY_MODE = 0x06
    CMD_DISPLAY_ON = 0x0C
    CMD_FUNCTION_SET_4BIT = 0x28
    CMD_SET_DDRAM = 0x80

    def __init__(self, i2c_bus=1, addr=LCD_I2C_ADDR):
        self.addr = addr
        self.backlight = self.BACKLIGHT
        self.i2c_handle = lgpio.i2c_open(i2c_bus, addr)

    def _write_byte(self, data):
        """Envia um byte pelo barramento I2C."""
        lgpio.i2c_write_byte(self.i2c_handle, data)

    def _pulse_enable(self, data):
        """Gera pulso no pino Enable para latchar dados no LCD."""
        self._write_byte(data | self.ENABLE | self.backlight)
        time.sleep(0.0005)
        self._write_byte((data & ~self.ENABLE) | self.backlight)
        time.sleep(0.0005)

    def _send_nibble(self, nibble, mode):
        """Envia 4 bits (nibble) ao LCD."""
        byte = (nibble & 0xF0) | mode | self.backlight
        self._pulse_enable(byte)

    def _send_byte(self, data, mode):
        """Envia um byte ao LCD em modo 4 bits (dois nibbles)."""
        self._send_nibble(data & 0xF0, mode)
        self._send_nibble((data << 4) & 0xF0, mode)

    def send_command(self, cmd):
        """Envia um comando ao LCD."""
        self._send_byte(cmd, self.RS_CMD)

    def send_char(self, char_code):
        """Envia um caractere ao LCD."""
        self._send_byte(char_code, self.RS_DATA)

    def init_display(self):
        """Inicializa o LCD no modo 4 bits."""
        time.sleep(0.05)

        # Sequência de inicialização para modo 4 bits (datasheet HD44780)
        for _ in range(3):
            self._send_nibble(0x30, self.RS_CMD)
            time.sleep(0.005)

        self._send_nibble(0x20, self.RS_CMD)
        time.sleep(0.005)

        self.send_command(self.CMD_FUNCTION_SET_4BIT)
        self.send_command(self.CMD_DISPLAY_ON)
        self.send_command(self.CMD_CLEAR)
        time.sleep(0.002)
        self.send_command(self.CMD_ENTRY_MODE)

    def clear(self):
        """Limpa o display."""
        self.send_command(self.CMD_CLEAR)
        time.sleep(0.002)

    def set_cursor(self, col, row):
        """Posiciona o cursor. Linha 0 = endereço 0x00, Linha 1 = 0x40."""
        offsets = [0x00, 0x40]
        if row < 0 or row >= LCD_ROWS:
            row = 0
        self.send_command(self.CMD_SET_DDRAM | (col + offsets[row]))

    def write_string(self, text):
        """Escreve uma string no LCD a partir da posição atual do cursor."""
        for char in text:
            self.send_char(ord(char))

    def display_line(self, row, text):
        """Escreve uma linha completa no LCD, preenchendo com espaços."""
        self.set_cursor(0, row)
        padded = text[:LCD_COLS].ljust(LCD_COLS)
        self.write_string(padded)

    def close(self):
        """Fecha o handle I2C."""
        try:
            lgpio.i2c_close(self.i2c_handle)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Classe do Sensor Ultrassônico HC-SR04
# ---------------------------------------------------------------------------

class UltrasonicSensor:
    """
    Driver para o sensor ultrassônico HC-SR04.

    Funcionamento:
      1. Envia pulso de 10us no pino TRIG
      2. Mede a duração do pulso HIGH no pino ECHO
      3. Calcula distância: d = (tempo * velocidade_do_som) / 2

    Nota: O pino ECHO do HC-SR04 opera em 5V. Utilizar divisor
    de tensão (resistores) para converter para 3.3V no GPIO do RPi.
    """

    SPEED_OF_SOUND_CM_PER_S = 34300.0  # cm/s a ~20°C
    TIMEOUT_S = 0.04  # Timeout de 40ms (~680cm max)

    def __init__(self, chip_handle, pin_trig, pin_echo):
        self.h = chip_handle
        self.pin_trig = pin_trig
        self.pin_echo = pin_echo

        lgpio.gpio_claim_output(self.h, self.pin_trig, level=0)
        lgpio.gpio_claim_input(self.h, self.pin_echo)

    def measure_distance_cm(self):
        """
        Mede a distância em centímetros.
        Retorna -1.0 em caso de timeout (sem obstáculo detectado).
        """
        # Garante TRIG em LOW
        lgpio.gpio_write(self.h, self.pin_trig, 0)
        time.sleep(0.002)

        # Envia pulso de 10us
        lgpio.gpio_write(self.h, self.pin_trig, 1)
        time.sleep(0.00001)
        lgpio.gpio_write(self.h, self.pin_trig, 0)

        # Aguarda início do pulso ECHO (rising edge)
        start = time.time()
        timeout_limit = start + self.TIMEOUT_S
        while lgpio.gpio_read(self.h, self.pin_echo) == 0:
            start = time.time()
            if start > timeout_limit:
                return -1.0

        # Aguarda fim do pulso ECHO (falling edge)
        end = start
        timeout_limit = end + self.TIMEOUT_S
        while lgpio.gpio_read(self.h, self.pin_echo) == 1:
            end = time.time()
            if end > timeout_limit:
                return -1.0

        # Calcula distância
        duration = end - start
        distance = (duration * self.SPEED_OF_SOUND_CM_PER_S) / 2.0
        return round(distance, 2)


# ---------------------------------------------------------------------------
# Classe do Teclado Matricial 4x4
# ---------------------------------------------------------------------------

class MatrixKeypad:
    """
    Driver para teclado matricial 4x4 via GPIO.

    Técnica de varredura:
      1. Configura todas as linhas como OUTPUT HIGH (inativas)
      2. Configura todas as colunas como INPUT com PULL_UP
      3. Para cada linha, coloca-a em LOW e lê as colunas
      4. Se uma coluna estiver LOW, a tecla na interseção está pressionada
      5. Aplica debouncing por tempo mínimo entre leituras
    """

    def __init__(self, chip_handle, row_pins, col_pins, keymap,
                 debounce_s=0.040):
        self.h = chip_handle
        self.row_pins = row_pins
        self.col_pins = col_pins
        self.keymap = keymap
        self.debounce_s = debounce_s
        self._held = None
        self._t_release = 0.0

        # Configura linhas como OUTPUT LOW (repouso)
        for pin in self.row_pins:
            lgpio.gpio_claim_output(self.h, pin, level=0)

        # Configura colunas como INPUT com PULL-DOWN
        for pin in self.col_pins:
            lgpio.gpio_claim_input(self.h, pin, lgpio.SET_PULL_DOWN)

    def scan_raw(self):
        """Varredura crua: uma passada pela matriz (Pull-Down, ativo-alto)."""
        for row_idx, row_pin in enumerate(self.row_pins):
            lgpio.gpio_write(self.h, row_pin, 1)
            time.sleep(0.00005)  # 50us para estabilizar

            for col_idx, col_pin in enumerate(self.col_pins):
                if lgpio.gpio_read(self.h, col_pin) == 1:
                    lgpio.gpio_write(self.h, row_pin, 0)
                    return self.keymap[row_idx][col_idx]

            lgpio.gpio_write(self.h, row_pin, 0)
            
        return None

    def scan(self):
        """Evento não-bloqueante: 1 caractere por pressão física."""
        k = self.scan_raw()
        agora = time.time()
        
        if k is not None:
            if self._held is None and (agora - self._t_release) >= self.debounce_s:
                self._held = k
                return k
            return None
            
        if self._held is not None:
            self._held = None
            self._t_release = agora
            
        return None


# ---------------------------------------------------------------------------
# Classe do Buzzer
# ---------------------------------------------------------------------------

class Buzzer:
    """Driver para buzzer passivo/ativo via GPIO digital (Não-bloqueante)."""

    def __init__(self, chip_handle, pin):
        self.h = chip_handle
        self.pin = pin
        self.is_on = False
        self.off_time = 0.0
        lgpio.gpio_claim_output(self.h, self.pin, level=0)

    def on(self):
        self.is_on = True
        lgpio.gpio_write(self.h, self.pin, 1)

    def off(self):
        self.is_on = False
        lgpio.gpio_write(self.h, self.pin, 0)

    def beep(self, duration_ms):
        """Inicia um bipe assíncrono (não-bloqueante)."""
        self.on()
        self.off_time = time.time() + (duration_ms / 1000.0)

    def update(self):
        """Verifica e desliga o buzzer se o tempo tiver expirado."""
        if self.is_on and time.time() >= self.off_time:
            self.off()

    def beep_pattern_blocking(self, on_ms, off_ms, count):
        """Emite um padrão de bipes (bloqueante - usar apenas no setup)."""
        for i in range(count):
            self.on()
            time.sleep(on_ms / 1000.0)
            self.off()
            if i < count - 1:
                time.sleep(off_ms / 1000.0)


# ---------------------------------------------------------------------------
# Máquina de Estados — Fechadura Eletrônica
# ---------------------------------------------------------------------------

class ElectronicLock:
    """
    Máquina de estados principal da fechadura eletrônica.

    Estados:
      IDLE       -> Aguarda entrada, monitora sensor
      INPUT      -> Recebendo dígitos da senha
      PROCESSING -> Validando a senha inserida
      SUCCESS    -> Acesso autorizado
      FAILURE    -> Acesso negado
      COOLDOWN   -> Bloqueio temporário após múltiplas falhas
      ALARM      -> Violação detectada pelo sensor
    """

    STATE_IDLE = "IDLE"
    STATE_INPUT = "INPUT"
    STATE_PROCESSING = "PROCESSING"
    STATE_SUCCESS = "SUCCESS"
    STATE_FAILURE = "FAILURE"
    STATE_COOLDOWN = "COOLDOWN"
    STATE_ALARM = "ALARM"

    def __init__(self):
        self.h = None
        self.lcd = None
        self.keypad = None
        self.sensor = None
        self.buzzer = None

        self.state = self.STATE_IDLE
        self.password_buffer = []
        self.password_hash = DEFAULT_PASSWORD_HASH
        self.failed_attempts = 0
        self.cooldown_start = 0.0
        self.state_enter_time = 0.0
        self.state_entered = False
        self.last_sensor_poll = 0.0
        self.door_locked = True
        self.alarm_active = False
        self.last_alarm_beep = 0.0

    def setup(self):
        """Inicializa todo o hardware."""
        print("[SETUP] Inicializando hardware...")

        # Abre o chip GPIO
        self.h = lgpio.gpiochip_open(0)
        print("[SETUP] GPIO chip aberto")

        # Inicializa o LCD via I2C
        self.lcd = LcdI2C()
        self.lcd.init_display()
        print("[SETUP] LCD I2C inicializado (0x{:02X})".format(LCD_I2C_ADDR))

        # Inicializa o teclado matricial
        self.keypad = MatrixKeypad(self.h, PIN_ROWS, PIN_COLS, KEYPAD_MAP)
        print("[SETUP] Teclado matricial configurado")

        # Inicializa o sensor ultrassônico
        self.sensor = UltrasonicSensor(self.h, PIN_TRIG, PIN_ECHO)
        print("[SETUP] Sensor ultrassônico configurado")

        # Inicializa o buzzer
        self.buzzer = Buzzer(self.h, PIN_BUZZER)
        print("[SETUP] Buzzer configurado")

        # Exibe mensagem inicial
        self.lcd.display_line(0, "   FECHADURA")
        self.lcd.display_line(1, "  ELETRONICA")
        time.sleep(2)

        # Bipe de inicialização
        self.buzzer.beep_pattern_blocking(100, 100, 2)

        self._enter_state(self.STATE_IDLE)
        print("[SETUP] Sistema pronto. Estado: IDLE")

    def _enter_state(self, new_state):
        """Transiciona para um novo estado."""
        old_state = self.state
        self.state = new_state
        self.state_enter_time = time.time()
        self.state_entered = True
        print(f"[STATE] {old_state} -> {new_state}")

    def _hash_password(self, password_str):
        """Calcula o hash SHA-256 de uma senha."""
        return hashlib.sha256(password_str.encode()).hexdigest()

    def _check_sensor(self):
        """
        Verifica o sensor ultrassônico para detectar violação.
        Quando a fechadura está trancada (door_locked=True),
        se a distância indicar porta aberta -> dispara alarme.
        """
        now = time.time()
        if now - self.last_sensor_poll < SENSOR_POLL_INTERVAL:
            return

        self.last_sensor_poll = now
        distance = self.sensor.measure_distance_cm()

        if distance < 0:
            # Timeout — sensor possivelmente desconectado
            return

        # Porta fisicamente aberta se distância > limiar
        door_open = distance > DOOR_CLOSED_THRESHOLD_CM

        if self.door_locked and door_open:
            # RF3: Violação — porta aberta enquanto deveria estar trancada
            print(f"[ALARM] Violação detectada! Distância: {distance:.1f} cm")
            if self.state != self.STATE_ALARM:
                self._enter_state(self.STATE_ALARM)
                self.alarm_active = True

    def _update_lcd_password(self):
        """Atualiza o LCD com asteriscos representando a senha digitada."""
        asterisks = '*' * len(self.password_buffer)
        if len(self.password_buffer) < MAX_PASSWORD_LENGTH:
            display = asterisks + '_'
        else:
            display = asterisks
        self.lcd.display_line(1, display)

    # --- Handlers de Estado ---

    def _handle_idle(self):
        """Estado IDLE: Aguarda primeira tecla, monitora sensor."""
        if self.state_entered:
            self.state_entered = False
            self.lcd.display_line(0, "STATUS: Trancada")
            self.lcd.display_line(1, "Pressione tecla")

        key = self.keypad.scan()
        if key is not None and key not in ('*', '#', 'A', 'B', 'C', 'D'):
            self.password_buffer = [key]
            self._enter_state(self.STATE_INPUT)
            self.lcd.display_line(0, "Digite a senha:")
            self._update_lcd_password()
            self.buzzer.beep(30)

    def _handle_input(self):
        """Estado INPUT: Recebe dígitos, backspace (*), confirma (#)."""
        key = self.keypad.scan()
        if key is None:
            return

        if key == '#':
            # RF1: Confirmar — submete a senha para processamento
            if len(self.password_buffer) >= MIN_PASSWORD_LENGTH:
                self.lcd.display_line(0, "Verificando...")
                self.lcd.display_line(1, "")
                self._enter_state(self.STATE_PROCESSING)
            else:
                self.lcd.display_line(1, "Minimo 4 digitos")
                self.buzzer.beep(100)
                # Removido o sleep() bloqueante. A mensagem ficará na tela
                # até o usuário pressionar a próxima tecla.

        elif key == '*':
            # RF1: Backspace — apaga último dígito
            if self.password_buffer:
                self.password_buffer.pop()
                self.buzzer.beep(20)
            self._update_lcd_password()
            if not self.password_buffer:
                self._enter_state(self.STATE_IDLE)

        elif key in ('A', 'B', 'C', 'D'):
            pass  # Teclas especiais — ignorar

        else:
            # Dígito numérico (0-9)
            if len(self.password_buffer) < MAX_PASSWORD_LENGTH:
                self.password_buffer.append(key)
                self.buzzer.beep(30)
                self._update_lcd_password()

    def _handle_processing(self):
        """Estado PROCESSING: Compara hash da senha."""
        password_str = ''.join(self.password_buffer)
        input_hash = self._hash_password(password_str)

        # Validação é instantânea, não utilizamos sleep() para não violar RF2
        # e evitar o congelamento do loop principal.
        if hmac.compare_digest(input_hash, self.password_hash):
            self._enter_state(self.STATE_SUCCESS)
        else:
            self._enter_state(self.STATE_FAILURE)

        self.password_buffer = []

    def _handle_success(self):
        """Estado SUCCESS: Acesso autorizado."""
        elapsed = time.time() - self.state_enter_time

        if self.state_entered:
            self.state_entered = False
            print("[ACCESS] Acesso AUTORIZADO")
            self.failed_attempts = 0
            self.door_locked = False

            # RF2: Atualiza LCD em < 200ms
            self.lcd.display_line(0, ">>> Aberto <<<")
            self.lcd.display_line(1, "STATUS: OK")

            # Bipe curto de sucesso
            self.buzzer.beep(BUZZ_SHORT_MS)

        elif elapsed >= MESSAGE_DISPLAY_TIME:
            self.door_locked = True
            self._enter_state(self.STATE_IDLE)

    def _handle_failure(self):
        """Estado FAILURE: Acesso negado."""
        elapsed = time.time() - self.state_enter_time

        if self.state_entered:
            self.state_entered = False
            self.failed_attempts += 1
            print(f"[ACCESS] Acesso NEGADO "
                  f"(tentativa {self.failed_attempts}/{MAX_FAILED_ATTEMPTS})")

            self.lcd.display_line(0, "Acesso Negado!")
            remaining = MAX_FAILED_ATTEMPTS - self.failed_attempts
            self.lcd.display_line(1, f"Resta(m) {remaining} tent.")

            # Bipe longo de falha
            self.buzzer.beep(BUZZ_LONG_MS)

        elif elapsed >= MESSAGE_DISPLAY_TIME:
            # RNF1: Verifica se atingiu limite de tentativas
            if self.failed_attempts >= MAX_FAILED_ATTEMPTS:
                self._enter_state(self.STATE_COOLDOWN)
                self.cooldown_start = time.time()
            else:
                self._enter_state(self.STATE_IDLE)

    def _handle_cooldown(self):
        """Estado COOLDOWN: Bloqueio temporário (RNF1)."""
        elapsed = time.time() - self.cooldown_start
        remaining = max(0, COOLDOWN_SECONDS - elapsed)

        self.lcd.display_line(0, "!! BLOQUEADO !!")
        self.lcd.display_line(1, f"Aguarde {int(remaining)}s")

        if remaining <= 0:
            self.failed_attempts = 0
            self._enter_state(self.STATE_IDLE)

    def _handle_alarm(self):
        """Estado ALARM: Violação física detectada (RF3)."""
        now = time.time()

        self.lcd.display_line(0, "!!! ALARME !!!")
        self.lcd.display_line(1, "Violacao detect.")

        # Bipes intermitentes
        if now - self.last_alarm_beep >= 0.5:
            self.buzzer.beep(BUZZ_ALARM_MS)
            self.last_alarm_beep = now

        # Verifica se a porta voltou a fechar (com throttling)
        if now - self.last_sensor_poll >= SENSOR_POLL_INTERVAL:
            self.last_sensor_poll = now
            distance = self.sensor.measure_distance_cm()
            if 0 <= distance <= DOOR_CLOSED_THRESHOLD_CM:
                print("[ALARM] Porta fechada. Alarme desativado.")
                self.alarm_active = False
                self._enter_state(self.STATE_IDLE)

    # --- Loop Principal ---

    def run(self):
        """Loop principal não-bloqueante da máquina de estados."""
        state_handlers = {
            self.STATE_IDLE: self._handle_idle,
            self.STATE_INPUT: self._handle_input,
            self.STATE_PROCESSING: self._handle_processing,
            self.STATE_SUCCESS: self._handle_success,
            self.STATE_FAILURE: self._handle_failure,
            self.STATE_COOLDOWN: self._handle_cooldown,
            self.STATE_ALARM: self._handle_alarm,
        }

        print("[RUN] Fechadura eletrônica em execução. CTRL+C para sair.")

        try:
            while True:
                # Atualiza periféricos não-bloqueantes
                if self.buzzer:
                    self.buzzer.update()

                # Monitora sensor continuamente (exceto durante alarme)
                if self.state != self.STATE_ALARM:
                    self._check_sensor()

                # Executa handler do estado atual
                handler = state_handlers.get(self.state)
                if handler:
                    handler()

                # Pequena pausa para não saturar a CPU
                time.sleep(0.01)

        except KeyboardInterrupt:
            print("\n[EXIT] Sinal de interrupção recebido.")
        # Cleanup delegado ao bloco main

    def cleanup(self):
        """Desliga todos os periféricos e libera recursos."""
        print("[CLEANUP] Desligando hardware...")
        if self.buzzer:
            self.buzzer.off()
        if self.lcd:
            self.lcd.clear()
            self.lcd.display_line(0, "Sistema deslig.")
            time.sleep(1)
            self.lcd.clear()
            self.lcd.close()
        if self.h is not None:
            lgpio.gpiochip_close(self.h)
        print("[CLEANUP] Recursos liberados.")


# ---------------------------------------------------------------------------
# Ponto de Entrada
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    lock = ElectronicLock()
    try:
        lock.setup()
        lock.run()
    except Exception as e:
        print(f"\n[ERRO CRÍTICO] Falha na execução: {e}")
    finally:
        lock.cleanup()
