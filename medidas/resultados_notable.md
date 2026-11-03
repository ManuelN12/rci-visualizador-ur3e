# Resultados · Notable (varios robots en la misma ventana)

**Fecha:** 3 de noviembre de 2026
**Script:** `python varios_robots.py --config config/ursim_y_falso.json` (entorno conda `ur3e`)

## Montaje

| Robot | Dónde | Dirección | Pose en la escena |
|---|---|---|---|
| `ursim` | URSim 5.25.2 en VirtualBox | 10.164.57.193:30001 | origen |
| `falso` | `herramientas/robot_falso.py` en el mismo portátil (otro Python, sin PyBullet) | 127.0.0.1:31001 | y = 0,8 m, girado 180° |

Los robots, sus IP, puertos y posiciones se leen del fichero JSON: no se toca el código.
Para la defensa, el segundo robot será el URSim de un compañero (solo cambia su IP en el fichero).

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

## Pruebas previas con dos robots falsos

Con dos robots falsos (uno de ellos enviando los bytes en trozos aleatorios) se comprobó además el caso de un robot
**colgado** (proceso detenido con SIGSTOP: conectado pero sin enviar): el aviso indica *conectado pero sin datos*, el
watchdog de la conexión la cierra a los 2 s y el otro robot sigue a 10 msg/s. Con `--interfaz tiempo_real` cada
receptor procesa ≈ 500 paquetes/s y el comportamiento ante caídas es el mismo.
