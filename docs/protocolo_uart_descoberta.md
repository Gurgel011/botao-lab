# Descoberta do protocolo UART

## O que foi confirmado

O produto comercial e vendido como modulo `UART TTL`.

Dados encontrados no anuncio e paginas relacionadas:

- Wisecoco / Wiseoco knob display.
- AMOLED `1.43"` / `466x466`.
- Touch suportado.
- Comunicacao com host por protocolo UART/porta serial TTL.
- A pagina do fabricante informa que ha manual de desenvolvimento secundario,
  ferramentas de software e suporte tecnico para integracao.

## O que nao respondeu

O probe textual seguro nao recebeu resposta para comandos como:

- `AT`
- `help`
- `status`
- `version`
- `info`
- `ping`

Bauds testados:

- `9600`
- `19200`
- `38400`
- `57600`
- `115200`
- `230400`
- `460800`
- `921600`

Conclusao: o protocolo nao parece ser AT/texto comum.

## Pacote binario de eventos

Pacotes capturados do aparelho:

```text
a5 3c 00 08 00 ...
```

Formato conhecido:

```text
bytes 0..4: header a5 3c 00 08 00
byte 5:    codigo do evento
byte 6:    flag
bytes 7..8: x little-endian
bytes 9..10: y little-endian
byte 11:   tail
byte 12:   checksum
```

Checksum:

```text
payload = bytes 5..11
checksum = (0xBB - (sum(payload) & 0xff)) & 0xff
```

## Proximo passo pratico

Capturar um host oficial falando com o modulo.

Ferramenta criada:

```bash
/home/paulo/botao-lab/uart_mitm.py
```

Uso:

```bash
/home/paulo/botao-lab/uart_mitm.py \
  --device /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0 \
  --baud 115200 \
  --link /tmp/botao_uart
```

Ela cria:

```text
/tmp/botao_uart
```

O app oficial/demo deve abrir `/tmp/botao_uart` em vez de abrir
`/dev/ttyUSB0`. A ferramenta registra tudo que o app envia e tudo que o aparelho
responde.

Teste local realizado: a ponte abriu `/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0`
e criou `/tmp/botao_uart`. Sem app/host conectado, nao ha bytes para registrar.

Logs:

```text
/home/paulo/botao-lab/logs/uart_mitm.log
/home/paulo/botao-lab/logs/uart_mitm.raw
```

## Analisador criado

Ferramenta:

```bash
/home/paulo/botao-lab/analyze_uart.py
```

Ela analisa:

- arquivos brutos `.bin` com bytes seriais diretos;
- arquivos `.raw` gerados pelo `uart_mitm.py`, preservando direcao
  `HOST_TO_DEVICE` e `DEVICE_TO_HOST`;
- frames conhecidos com header `a5 3c 00 08 00`;
- contagem de codigos de evento;
- faixa de coordenadas;
- checksums invalidos;
- blocos desconhecidos que podem ser comandos de tela.

Resultados dos logs existentes:

| Arquivo | Frames validos | Codigos | Checksum ruim | Coordenadas |
| --- | ---: | --- | ---: | --- |
| `touch.bin` | 22 | `0x00`, `0x05`, `0x0a` | 0 | x `0..501`, y `0..253` |
| `mapeamento-01.bi` | 30 | `0x00`, `0x01`, `0x03`, `0x04`, `0x05`, `0x07`, `0x09` | 0 | x `0..501`, y `0..256` |

Relatorios JSON gerados:

```text
/home/paulo/botao-lab/logs/touch.analysis.json
/home/paulo/botao-lab/logs/mapeamento-01.analysis.json
```

## Captura guiada

Ferramenta:

```bash
/home/paulo/botao-lab/capture_protocol.py --seconds 60 --json
```

Fluxo:

1. Abre a ponte entre `/tmp/botao_uart` e o aparelho real.
2. Aguarda o app/demo oficial conversar pela porta virtual.
3. Salva `uart_mitm.log` e `uart_mitm.raw`.
4. Analisa automaticamente o `.raw`.
5. Salva `/home/paulo/botao-lab/logs/uart_mitm.analysis.json` quando usado
   com `--json`.

Teste local:

- a ponte abriu e fechou corretamente;
- sem app/demo conectado, o log bruto ficou vazio;
- isso confirma o fluxo, mas ainda nao revela comandos de tela.
