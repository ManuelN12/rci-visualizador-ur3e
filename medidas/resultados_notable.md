# Resultados · Notable (varios robots en la misma ventana)

**Fecha:** 3 de noviembre de 2026
**Script:** `python varios_robots.py --config config/ursim_y_falso.json` (entorno conda `ur3e`)

## Montaje

| Robot | Dónde | Dirección | Pose en la escena |
|---|---|---|---|
| `ursim` | URSim 5.25.2 en VirtualBox | 10.164.57.193:30001 | origen |
| `falso` | `herramientas/robot_falso.py` en el mismo portátil (otro Python, sin PyBullet) | 127.0.0.1:31001 | y = 0,8 m, girado 180° |

Los robots, sus IP, puertos y posiciones se leen del fichero JSON: no se toca el código.
El 11 de noviembre se repitió con el URSim de un compañero (sección siguiente): solo cambiaron las IP del fichero.

## Arquitectura

- Un hilo `ReceptorRobot` por robot (`receptor.py`), con su socket y su búfer: solo **escribe** el último estado.
- El hilo principal **lee** una copia de cada estado a 30 Hz y es el único que llama a PyBullet.
- El estado compartido se protege con `threading.Lock`; dentro de la sección crítica solo se asignan valores.
- Watchdog: más de 1 s sin datos → el robot simulado se queda quieto, se pinta de rojo y se avisa por consola.

## Funcionamiento normal

```
--- 12:38:30 ---
  ursim        OK          7.8 msg/s   último dato hace   0.0 s  RUNNING  q(°)  -91.7  -99.0 -126.2  -46.3   91.4   -1.8
  falso        OK         10.0 msg/s   último dato hace   0.1 s  RUNNING  q(°)   34.3  -91.0   -2.2 -112.5  -29.1  -43.2
```

Los dos robots aparecen en la misma ventana y cada uno sigue a su robot real. `ursim` envía ≈ 7,6–8 mensajes/s en lugar
de 10 porque la VM va justa de recursos (como en el bloque B); el falso, que corre en Windows, envía sus 10/s.

## Desconexión de un robot

1. Ctrl + C en el robot falso → su robot simulado se pone **rojo y se queda quieto**; aviso `⚠ falso: SIN DATOS`.
2. Mientras tanto, el robot de URSim **sigue moviéndose** con normalidad desde la pestaña *Move*.
3. Al relanzar el robot falso, el programa se reconecta solo, el robot recupera su color y vuelve a moverse
   (`✓ falso: recibiendo datos`).

**Un robot que se desconecta no detiene a los demás.**

## Prueba con dos URSim (el mío y el de un compañero) · 11 de noviembre de 2026

**Script:** `python varios_robots.py --config config/dos_ursim.json`

### Montaje en la red del aula (10.172.18.0/24)

| Equipo | IP |
|---|---|
| Mi portátil (cliente), por cable | 10.172.18.61 |
| Mi VM (`manuel`) | 10.172.18.62 |
| VM del compañero (`companero`) | 10.172.18.59 |

Primero se intentó con mi portátil en el Wi‑Fi (10.164.51.207/20): `ping` y `Test-NetConnection -Port 30001` a la VM del
compañero dieron **timeout**. El Wi‑Fi y la red del aula son redes distintas y la universidad no deja pasar el tráfico
entre ellas (*timed out*, no *unreachable*: se descarta en un cortafuegos). Solución: conectar el portátil por cable al
aula, poner el puente de la VM sobre la tarjeta Ethernet (*Realtek PCIe GbE*) y reiniciarla para que pidiera una IP nueva
por DHCP. Después, `ping 10.172.18.59`: 4/4, < 1 ms, TTL = 64.

Las dos VM tienen MAC distintas (`…:12:9e` y `…:1c:69`), así que no hay conflicto en el switch.

### Resultado

```
[15:51:25] manuel: conectado a 10.172.18.62:30001 desde 10.172.18.61:61359
[15:51:25] companero: conectado a 10.172.18.59:30001 desde 10.172.18.61:61360
[15:51:25] ✓ manuel: recibiendo datos
[15:51:25] ✓ companero: recibiendo datos
--- 15:51:51 ---
  manuel       OK  8.3 msg/s  último dato hace 0.0 s  RUNNING    q(°)  -91.7  -99.0 -126.2 -46.3 91.4 -1.8
  companero    OK 10.0 msg/s  último dato hace 0.1 s  RUNNING    q(°) -113.5  -99.0 -126.2 -46.3 91.4 -1.8
--- 15:52:01 ---
  companero    OK  9.8 msg/s  último dato hace 0.0 s  POWER_OFF  q(°) -118.0 -111.0 -126.2 -46.3 91.4 -1.8
[15:52:08] ⚠ companero: SIN DATOS (conectado pero sin datos); su robot simulado se queda quieto y en rojo
[15:52:09] companero: conexión cerrada: sin datos desde hace 2.0 s (robot colgado o red caída)
[15:52:11] companero: no se puede conectar a 10.172.18.59:30001 (timed out); reintento en 2 s
--- 15:53:16 ---
  manuel       OK  7.0 msg/s  último dato hace 0.1 s  RUNNING    q(°)  -91.7  -99.0 -126.2 -46.3 91.4 -1.7
  companero    SIN DATOS 0.0 msg/s  último dato hace 68.5 s  POWER_OFF
```

1. Los dos robots aparecen en la misma ventana (`notable_dos_ursim.png`), cada uno con su pose del fichero, y cada uno
   sigue a su URSim: el compañero movió base y hombro (−91,7° → −118°, −99° → −111°) y solo se movió su modelo.
2. Con el brazo del compañero apagado (`POWER_OFF`) los datos siguen llegando: el controlador publica el estado igual.
3. Al cortar la red del compañero, a 1 s sin datos su modelo se queda quieto y **rojo** (`notable_companero_sin_datos.png`);
   a los 2 s el watchdog de la conexión la cierra y el receptor reintenta cada 2 s (*timed out*).
4. Mientras tanto mi robot sigue a ≈ 9 msg/s y lo muevo desde *Move*: **la caída de un robot no afecta al otro**.
5. Al volver a conectar la red del compañero, su robot recupera el color y vuelve a moverse (comprobado en pantalla; el
   registro guardado termina antes de la reconexión).

Al mover un robot desde la pestaña *Move* aparecen avisos `PROGRAM_XXX_STARTED inkognito` / `STOPPED`: PolyScope
ejecuta cada pulsación de los botones de movimiento como un pequeño programa interno con ese nombre.

## Pruebas previas con dos robots falsos

Con dos robots falsos (uno de ellos enviando los bytes en trozos aleatorios) se comprobó además el caso de un robot
**colgado** (proceso detenido con SIGSTOP: conectado pero sin enviar): el aviso indica *conectado pero sin datos*, el
watchdog de la conexión la cierra a los 2 s y el otro robot sigue a 10 msg/s. Con `--interfaz tiempo_real` cada
receptor procesa ≈ 500 paquetes/s y el comportamiento ante caídas es el mismo.
