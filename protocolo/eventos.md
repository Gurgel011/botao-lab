# Eventos observados

Preencher uma linha para cada gesto ou comando testado.

| Data/hora | Baud | Acao | Bytes hex | Texto | Observacao |
| --- | ---: | --- | --- | --- | --- |
| | 115200 | repouso | | | |
| | 115200 | clique curto | | | |
| | 115200 | clique longo | | | |
| | 115200 | giro direita | | | |
| | 115200 | giro esquerda | | | |
| | 115200 | touch centro | | | |
| | 115200 | touch borda | | | |
| | 115200 | comando AT | | | |
| | 115200 | comando help | | | |
| | 115200 | comando status | | | |

## Mapeamento 01

Arquivo bruto:

```text
./logs/mapeamento-01.bi
```

Analise decodificada:

```text
./protocolo/mapeamento-01.txt
```

Descobertas:

- O protocolo e binario, nao texto.
- Cada pacote tem 13 bytes.
- Todos os pacotes observados comecam com `a5 3c 00 08 00`.
- O byte 6, contando a partir de zero, parece ser o tipo do evento:
  - `00`: repouso/soltar/inativo.
  - `01`: pressionar/inicializacao.
  - `03`: gesto ainda nao identificado.
  - `04`: gesto ainda nao identificado.
  - `05`, `07`, `09`: ponto/touch com coordenadas.
- Coordenadas provaveis em little-endian:
  - `x`: bytes 7 e 8.
  - `y`: bytes 9 e 10.
- O ultimo byte parece checksum ou validacao.
- Checksum confirmado nos logs:
  - payload = bytes 5..11 do pacote.
  - `checksum = (0xBB - (sum(payload) & 0xff)) & 0xff`.
  - Exemplo: pacote repouso `00 00 00 00 00 00 01` soma `0x01`,
    checksum `0xBA`.
- Analise automatica:
  - `./analyze_uart.py`.
  - `touch.bin`: 22 frames validos, checksum ruim `0`.
  - `mapeamento-01.bi`: 30 frames validos, checksum ruim `0`.
  - relatorios JSON em `./logs/*.analysis.json`.

Exemplos reais:

| Evento bruto | Interpretacao atual |
| --- | --- |
| `a5 3c 00 08 00 04 00 00 00 00 00 00 b7` | gesto `04`, possivelmente giro ou clique |
| `a5 3c 00 08 00 03 00 00 00 00 00 00 b8` | gesto `03`, possivelmente giro ou clique |
| `a5 3c 00 08 00 05 01 24 01 42 00 00 4e` | ponto/touch em `x=292`, `y=66` |
| `a5 3c 00 08 00 00 00 00 00 00 00 01 ba` | repouso/soltar |

## Hipoteses

- USB e serial passam pelo CH340/CH341.
- O chip principal parece ser FR8008GP, entao nao tratar como ESP32 ate haver
  confirmacao fisica de outro chip Espressif.
- Pads `OPA_TX` e `OPA_RX` provavelmente sao UART do aparelho.
- O componente `24.000` e provavelmente cristal de 24 MHz.
