sequenceDiagram
    autonumber
    actor User as Usuário (Navegador)
    box Gray Frontend (Navegador)
        participant UI as Interface Web (HTML)
        participant JS as JavaScript (Script)
    end
    box DarkSlatedray Backend (ESP32 Firmware)
        participant Server as WebServer (Rotas)
        participant CPP as Função handleCalculadora()
        participant Aux as Função converterBinarioParaInteiro()
        participant HW as Saídas Digitais (GPIOs)
    end

    User->>UI: Insere Strings Binárias (ex: A="0111", B="0010")
    User->>UI: Clica nos botões "SOMAR" ou "SUBTRAIR"
    UI->>JS: Dispara evento onclick
    activate JS
    Note over JS: Função: enviarOperacao(op)<br/>Validação via Regex: /^[01]{4}$/
    
    JS->>Server: Requisição HTTP GET /calc?a=0111&b=0010&op=add
    deactivate JS
    activate Server
    
    Note over Server: server.on("/calc", HTTP_GET, handleCalculadora)
    Server->>CPP: Encaminha execução do cliente
    deactivate Server
    activate CPP
    
    Note over CPP: Coleta os argumentos textuais:<br/>server.arg("a"), server.arg("b"), server.arg("op")
    
    CPP->>Aux: Chama para Operando A ("0111")
    activate Aux
    Note over Aux: strtol() converte para decimal.<br/>Se bit 3 for 1, aplica complemento de 2 ( | 0xF0 )
    Aux-->>CPP: Retorna int8_t (7)
    deactivate Aux

    CPP->>Aux: Chama para Operando B ("0010")
    activate Aux
    Aux-->>CPP: Retorna int8_t (2)
    deactivate Aux

    Note over CPP: Realiza Operação (resultado = 7 + 2 = 9)<br/>Valida Overflow: se (resultado < -8 ou resultado > 7)
    Note over CPP: Isola os 4 bits físicos: bitsExibicao = resultado & 0x0F (9 vira 1001)

    loop Para i de 0 até 3
        CPP->>HW: digitalWrite(LED_PINS[i], bit_da_posicao_i)
        activate HW
        Note over HW: LEDs Físicos acendem na placa (Pinos 7, 6, 5, 4)
        deactivate HW
    end

    Note over CPP: Constrói Payload JSON estruturado:<br/>{"resDec":-7, "resBin":"1001", "overflow":true}
    
    CPP->>Server: server.send(200, "application/json", jsonResponse)
    activate Server
    Server-->>JS: Retorna Resposta HTTP 200 OK (JSON)
    deactivate Server
    deactivate CPP
    activate JS
    
    Note over JS: .then(res => res.json())<br/>Processa dados e adiciona a classe CSS '.overflow' se verdadeiro
    JS->>UI: Modifica o DOM (#resDec, #resBin, #status)
    UI-->>User: Exibe o resultado (-7), binário (1001) e o alerta: ⚠️ OVERFLOW!
    deactivate JS