# botao-lab

Laboratorio independente para mapear e controlar o aparelho sem alterar o
`photopainter-official`.

## Objetivo

Dar autonomia ao usuario sobre:

- controle externo: clique, giro, comandos pelo computador;
- controle interno: touch/display/sensor do aparelho;
- protocolo: mensagens que entram e saem pela serial USB;
- automacoes: transformar eventos do aparelho em acoes no computador.

## Regra de seguranca

Por enquanto, nao gravar firmware no aparelho. O hardware parece usar FR8008 +
CH340, nao ESP32 comum. A primeira fase e apenas ouvir e mapear.

## Comecar

A porta esta em:

```bash
/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
```

Se estiver ocupada, veja quem esta usando:

```bash
fuser -v /dev/ttyUSB0
```

Para liberar a porta, pare o processo que aparece no `fuser`. No ultimo teste,
era o PID `941375`.

## Mapear eventos

Ouvir em texto:

```bash
/home/paulo/botao --monitor --duration 20
```

Ouvir em hexadecimal, melhor para protocolo binario:

```bash
/home/paulo/botao --monitor --hex --duration 20
```

Salvar log bruto:

```bash
/home/paulo/botao --monitor --hex --duration 30 \
  --log /home/paulo/botao-lab/logs/mapeamento-01.bin
```

Testar baud rates comuns:

```bash
/home/paulo/botao --scan-bauds --duration 3
```

## Sequencia de descoberta

1. Ligar o aparelho sem tocar em nada e gravar 10 segundos.
2. Fazer clique curto e gravar.
3. Fazer clique longo e gravar.
4. Girar para direita devagar e gravar.
5. Girar para esquerda devagar e gravar.
6. Tocar no touch/display em pontos diferentes e gravar.
7. Enviar comandos simples: `AT`, `help`, `status`, `?`.

## Enviar comandos

```bash
/home/paulo/botao --line "AT" --hex
/home/paulo/botao --line "help" --hex
/home/paulo/botao --line "status" --hex
```

## Descobrir protocolo UART

Probe seguro com comandos somente de identificacao/leitura:

```bash
/home/paulo/botao-lab/uart_protocol_probe.py
```

Log:

```text
/home/paulo/botao-lab/logs/uart_protocol_probe.log
```

Esse probe nao envia `erase`, `flash`, `write`, `reset`, `reboot` ou `update`.

Ponte para capturar um app/host oficial conversando com o aparelho:

```bash
/home/paulo/botao-lab/uart_mitm.py \
  --device /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0 \
  --baud 115200 \
  --link /tmp/botao_uart
```

Depois aponte o app oficial para:

```text
/tmp/botao_uart
```

Logs:

```text
/home/paulo/botao-lab/logs/uart_mitm.log
/home/paulo/botao-lab/logs/uart_mitm.raw
```

Observacao: os logs so recebem dados quando algum app/host abre
`/tmp/botao_uart` e conversa com o aparelho. Se a ponte for aberta sozinha, ela
apenas cria a porta virtual e fica aguardando trafego.

Analisar capturas UART:

```bash
/home/paulo/botao-lab/analyze_uart.py /home/paulo/botao-lab/logs/touch.bin
/home/paulo/botao-lab/analyze_uart.py /home/paulo/botao-lab/logs/uart_mitm.raw
```

Gerar relatorio JSON:

```bash
/home/paulo/botao-lab/analyze_uart.py /home/paulo/botao-lab/logs/touch.bin --json
```

Captura guiada completa, com ponte + analise automatica:

```bash
/home/paulo/botao-lab/capture_protocol.py --seconds 60 --json
```

Durante esses 60 segundos, o app/demo oficial deve abrir `/tmp/botao_uart`.
Quando houver trafego, a ferramenta analisa automaticamente
`/home/paulo/botao-lab/logs/uart_mitm.raw`.

## Play/Pause com touch

Aplicacao visual com logo da Antena 1 e escolha de acao do usuario:

```bash
/home/paulo/botao-lab/antena1_touch.py
```

Opcoes disponiveis na janela:

- `Alternar Play/Pause`: cada toque alterna o estado.
- `Sempre Play`: todo toque envia play.
- `Sempre Pause`: todo toque envia pause.
- `Somente visual`: nao envia comando ao player, apenas mostra o evento.

A escolha fica salva em:

```text
/home/paulo/botao-lab/config/play_pause.json
```

## Autonomia por regioes do touch

Painel para o usuario escolher a acao de cada regiao do touch:

```bash
/home/paulo/botao-lab/touch_autonomy.py
```

Configuracao salva em:

```text
/home/paulo/botao-lab/config/touch_autonomy.json
```

Regioes atuais:

- `centro`
- `cima`
- `baixo`
- `esquerda`
- `direita`
- `fora_zona`

## Motor de funcoes do usuario

Daemon sem interface grafica para ligar regioes do touch a funcoes nomeadas:

```bash
/home/paulo/botao-lab/botao_functions.py
```

Configuracao:

```text
/home/paulo/botao-lab/config/user_functions.json
```

Tipos de funcao suportados:

- `media`: `toggle`, `play`, `pause`, `next`, `previous`.
- `log`: registra o toque no arquivo de log.
- `shell`: executa comando local somente com `--allow-shell`.
- `serial_write`: escreve bytes na UART somente com `--allow-serial-write`.

Por padrao, funcoes que podem alterar o sistema ou enviar comandos desconhecidos
ao aparelho ficam bloqueadas.

## Arquivos

- `logs/`: capturas brutas da serial.
- `analyze_uart.py`: analisador de capturas brutas e capturas MITM.
- `capture_protocol.py`: captura guiada com ponte UART e analise automatica.
- `protocolo/eventos.md`: tabela manual de eventos descobertos.

## Dependências

- Python 3.
- `pyserial` para comunicação UART.
- Tkinter para as interfaces visuais.
- `playerctl` quando as ações de mídia forem usadas no Linux.

Instalação mínima em ambiente virtual:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install pyserial
```

## Organização dos resultados

- `config/`: escolhas persistentes do usuário.
- `docs/`: procedimentos e conclusões consolidadas.
- `logs/`: capturas brutas e relatórios gerados; não devem ser editados manualmente.
- `protocolo/`: formato dos frames, zonas de toque e eventos confirmados.

Uma hipótese só deve ser registrada como confirmada em `protocolo/` depois de
ser reproduzida em mais de uma captura. Preserve o arquivo bruto usado na
conclusão para permitir uma análise posterior.
- `config/play_pause.json`: escolha atual do usuario para o touch.
- `config/touch_autonomy.json`: acoes por regiao do touch.
- `config/user_functions.json`: motor de funcoes do usuario.
