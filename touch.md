# Touch

Foco atual: entender e controlar a parte interna de touch do aparelho.

## Protocolo observado

Pacotes de touch usam 13 bytes:

```text
a5 3c 00 08 00 TT FF XX XX YY YY 00 CC
```

Campos provaveis:

- `TT`: tipo do evento. Foram vistos `05`, `07` e `09` para touch/ponto.
- `FF`: flag/estado do toque.
- `XX XX`: coordenada X em little-endian.
- `YY YY`: coordenada Y em little-endian.
- `CC`: checksum ou byte de validacao.

Faixa observada ate agora:

- `x`: 0 a 501
- `y`: 7 a 253

Codigos observados com coordenadas:

- `05`: touch/ponto comum.
- `0a`: tambem carrega coordenadas e deve ser tratado como touch.

## Mapa ao vivo

```bash
/home/paulo/botao --touch-map --duration 30 \
  --csv /home/paulo/botao-lab/logs/touch.csv \
  --log /home/paulo/botao-lab/logs/touch.bin
```

Esse modo mostra so eventos de touch e salva:

- bytes brutos em `touch.bin`;
- coordenadas decodificadas em `touch.csv`.

## Calibracao sugerida

Fazer um toque por vez:

1. centro;
2. cima;
3. baixo;
4. esquerda;
5. direita;
6. borda superior esquerda;
7. borda superior direita;
8. borda inferior esquerda;
9. borda inferior direita.

Depois disso, as regioes de `touch_zones.json` podem virar funcoes reais.

Calibracao guiada, com rótulos e salvamento automático:

```bash
/home/paulo/botao-lab/touch_calibrate.py
```

Ela salva:

```text
/home/paulo/botao-lab/logs/touch_calibration.csv
/home/paulo/botao-lab/protocolo/touch_zones_calibrated.json
```

## Acoes por zona

Rodar classificador ao vivo:

```bash
/home/paulo/botao-lab/touch_actions.py
```

Rodar por tempo limitado:

```bash
/home/paulo/botao-lab/touch_actions.py --duration 30
```

Saida esperada:

```text
touch x=222 y=144 code=05 flag=00 zone=centro action=touch_center
```

Zonas configuradas em:

```text
/home/paulo/botao-lab/protocolo/touch_zones.json
```

## Antena 1 Play/Pause

App visual com o logo da Antena 1 no topo. Cada toque no touch alterna
`PLAY`/`PAUSE`.

Antes, libere a serial se outro processo estiver usando:

```bash
fuser -v /dev/ttyUSB0
kill <PID>
```

Rodar:

```bash
/home/paulo/botao-lab/antena1_touch.py
```

Modo visual apenas, sem enviar comando para players do sistema:

```bash
/home/paulo/botao-lab/antena1_touch.py --no-media
```

O app tenta enviar Play/Pause via MPRIS/DBus para players compatíveis. Se não
houver player detectado, ele ainda atualiza a interface visual.
