# Botão Lab

`Python` · `UART` · `Touch` · `Engenharia reversa`

[Começar](#comecar) · [Dependências](#dependências) · [Protocolo](#descobrir-protocolo-uart) · [← Todos os projetos](https://github.com/Gurgel011#projetos)

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

Descubra a porta do aparelho:

```bash
ls /dev/serial/by-id/
```

Todos os scripts deste repositório aceitam `--device <porta>` e também leem a
variável de ambiente `BOTAO_DEVICE` (padrão: `/dev/ttyUSB0`):

```bash
export BOTAO_DEVICE=/dev/serial/by-id/<o-seu-aqui>
```

Se a porta estiver ocupada, veja quem está usando e pare o processo:

```bash
fuser -v /dev/ttyUSB0
```

## Mapear eventos

> Os comandos `--monitor`, `--scan-bauds` e `--line` abaixo pertencem a um
> binário externo (`botao`), que não faz parte deste repositório e não estava
> mais presente na máquina no momento desta revisão. Os scripts Python
> equivalentes e mantidos aqui são `uart_protocol_probe.py` (probe seguro),
> `capture_protocol.py` (captura guiada) e `touch_calibrate.py` (calibração) —
> use-os se o binário `botao` não estiver disponível.

Ouvir em texto:

```bash
botao --monitor --duration 20
```

Ouvir em hexadecimal, melhor para protocolo binario:

```bash
botao --monitor --hex --duration 20
```

Salvar log bruto:

```bash
botao --monitor --hex --duration 30 \
  --log ./logs/mapeamento-01.bin
```

Testar baud rates comuns:

```bash
botao --scan-bauds --duration 3
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
botao --line "AT" --hex
botao --line "help" --hex
botao --line "status" --hex
```

## Descobrir protocolo UART

Probe seguro com comandos somente de identificacao/leitura:

```bash
./uart_protocol_probe.py
```

Log:

```text
./logs/uart_protocol_probe.log
```

Esse probe nao envia `erase`, `flash`, `write`, `reset`, `reboot` ou `update`.

Ponte para capturar um app/host oficial conversando com o aparelho:

```bash
./uart_mitm.py \
  --device "$BOTAO_DEVICE" \
  --baud 115200 \
  --link /tmp/botao_uart
```

Depois aponte o app oficial para:

```text
/tmp/botao_uart
```

Logs:

```text
./logs/uart_mitm.log
./logs/uart_mitm.raw
```

Observacao: os logs so recebem dados quando algum app/host abre
`/tmp/botao_uart` e conversa com o aparelho. Se a ponte for aberta sozinha, ela
apenas cria a porta virtual e fica aguardando trafego.

Analisar capturas UART:

```bash
./analyze_uart.py ./logs/touch.bin
./analyze_uart.py ./logs/uart_mitm.raw
```

Gerar relatorio JSON:

```bash
./analyze_uart.py ./logs/touch.bin --json
```

Captura guiada completa, com ponte + analise automatica:

```bash
./capture_protocol.py --seconds 60 --json
```

Durante esses 60 segundos, o app/demo oficial deve abrir `/tmp/botao_uart`.
Quando houver trafego, a ferramenta analisa automaticamente
`./logs/uart_mitm.raw`.

## Play/Pause com touch

Aplicacao visual com logo da Antena 1 e escolha de acao do usuario:

```bash
./antena1_touch.py
```

Opcoes disponiveis na janela:

- `Alternar Play/Pause`: cada toque alterna o estado.
- `Sempre Play`: todo toque envia play.
- `Sempre Pause`: todo toque envia pause.
- `Somente visual`: nao envia comando ao player, apenas mostra o evento.

A escolha fica salva em:

```text
./config/play_pause.json
```

## Autonomia por regioes do touch

Painel para o usuario escolher a acao de cada regiao do touch:

```bash
./touch_autonomy.py
```

Configuracao salva em:

```text
./config/touch_autonomy.json
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
./botao_functions.py
```

Configuracao:

```text
./config/user_functions.json
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
