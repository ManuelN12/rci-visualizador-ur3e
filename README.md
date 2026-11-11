# Visualizador de un UR3e por TCP/IP

**Asignatura:** Redes de Comunicación Industriales · Máster en Electrónica Industrial · Universidad de Deusto
**Alumno:** Manuel Narváez
**Curso:** 2026–2027

Programa en Python que se conecta por TCP/IP a un robot UR3e (real o simulado con URSim), decodifica byte a byte
los mensajes binarios que emite y reproduce su configuración articular en el simulador PyBullet.

## Estado

| Nivel | Requisitos | Estado |
|---|---|---|
| Aprobado (5) | `primaria.py` (30001) y `tiempo_real.py` (30003), con búfer y delimitación por longitud | ✅ Validado con URSim 5.25.2 (hitos A0–A5, B1–B4 y reinicio de URSim). Resultados en `medidas/` |
| Notable (7) | Varios robots en la misma ventana, configurados por fichero, uno por hilo | ✅ `varios_robots.py` probado con URSim + robot falso (desconexión de uno sin afectar al otro). Pendiente: repetir con el URSim de un compañero |
| Sobresaliente (10) | Envío de órdenes URScript y mini-aplicación «Enseñar y reproducir» | ✅ `ensenar_reproducir.py` validado con URSim (4 puntos, error provocado apagando el robot). Pendiente: UR3e real con el profesor |

## Estructura

```
├── primaria.py            Bloque A · interfaz primaria (puerto 30001, 10 Hz)
├── tiempo_real.py         Bloque B · interfaz de tiempo real (puerto 30003, 500 Hz)
├── varios_robots.py       Bloque C · notable: varios robots, un hilo receptor por robot
├── receptor.py            Hilo receptor de un robot (último estado protegido con Lock)
├── ensenar_reproducir.py  Bloque D · sobresaliente: enseñar, previsualizar, ejecutar y supervisar
├── consola_ur3e.bat       Doble clic: consola con el entorno conda ur3e (PyBullet) en esta carpeta
├── ur_protocolo.py        Decodificación: búfer, mensajes, subpaquetes, tiempo real (sin red)
├── ur_conexion.py         Conexión TCP: búfer, watchdog de silencio y reconexión automática
├── visor.py               Envoltorio del visualizador PyBullet (convenio de ángulos, copias de listas)
├── configuracion.py       Lectura del fichero de robots
├── config/
│   ├── robots.json        IP y puertos de los robots (URSim del aula o UR3e real)
│   └── robot_falso.json   Para probar en casa con el robot falso
├── herramientas/
│   └── robot_falso.py     Servidor que imita las interfaces 30001 y 30003 de un UR3e
├── medidas/               Registros y salidas para la memoria
└── docs/                  Chuleta del aula y notas
```

## Instalación

Requiere Python 3.9 o posterior y el visualizador `ur3e_rg2-0.1.0-py3-none-any.whl` (aula virtual).

```bash
python -m venv venv
venv\Scripts\activate                 # Windows  (Linux: source venv/bin/activate)
pip install ur3e_rg2-0.1.0-py3-none-any.whl
```

> **Nota Windows:** `pybullet` no publica instaladores precompilados para Windows con versiones recientes de Python.
> Si `pip` falla al compilarlo, hacen falta las *Build Tools* de Visual Studio, o usar un Python con
> `pybullet` ya compilado (por ejemplo, conda-forge). Los modos sin visor (`--modo bytes`, `mensajes`,
> `subpaquetes`, `angulos`…) **no necesitan PyBullet**.

## Configuración

La IP del robot se cambia en `config/robots.json`, **sin tocar el código**:

```json
{
    "robots": [
        { "nombre": "ursim", "ip": "10.172.18.178", "puerto_primaria": 30001, "puerto_tiempo_real": 30003,
          "pose": [0, 0, 0, 0, 0, 0] }
    ],
    "convenio_angulos": { "signo": [1, 1, 1, 1, 1, 1], "desfase_grados": [0, 0, 0, 0, 0, 0] }
}
```

- `pose`: posición de la base del robot simulado en la escena: `[x, y, z]` en metros y `[roll, pitch, yaw]` en radianes.
- `convenio_angulos`: corrección si alguna articulación del modelo de PyBullet tuviera otro origen o sentido
  (`q_modelo = signo · q_ur + desfase`).
- Otro fichero: `--config ruta.json`. Otro robot de la lista: `--robot nombre`.
- Los ficheros JSON pueden estar guardados con BOM (Bloc de notas, PowerShell): `configuracion.py` los lee con `utf-8-sig`.

## Uso

Cada hito del enunciado tiene su modo:

| Hito | Orden | Qué comprobar |
|---|---|---|
| A1 | `python primaria.py --modo bytes` | Los bytes de cada `recv()` no coinciden siempre con un mensaje |
| A2 | `python primaria.py --modo mensajes` | Primero un tipo 20 (versión); después tipos 16 a 10 Hz, todos de la misma longitud |
| A3 | `python primaria.py --modo subpaquetes` | Los subpaquetes suman exactamente la longitud del mensaje menos 5 (✓) |
| A4 | `python primaria.py --modo angulos` | Los 6 ángulos coinciden con la pestaña *Mover* de PolyScope |
| A5 | `python primaria.py` | El robot de PyBullet sigue al de URSim |
| B1 | `python tiempo_real.py --modo paquetes` | Todos los paquetes tienen la misma longitud |
| B2 | `python tiempo_real.py --modo frecuencia` | Unos 500 paquetes por segundo (menos si URSim no va a tiempo real) y `recv llenos` = 0 |
| B3 | `python tiempo_real.py --modo angulos` | Coinciden con los de `primaria.py` |
| B4 | `python tiempo_real.py` | Tras mover rápido el robot, el simulado no acumula retraso |

Para la pregunta 1 de la memoria: `python primaria.py --modo bytes --registro medidas/recv_primaria.csv`
guarda en CSV la hora y los bytes de cada `recv()`.

Ctrl + C para salir.

### Varios robots (notable)

```bash
python varios_robots.py --config config/robots.json                      # todos los robots del fichero
python varios_robots.py --config config/robots.json --interfaz tiempo_real
python varios_robots.py --config config/ursim_y_falso.json               # URSim + robot falso en el mismo PC
```

Cada robot se recibe en su propio hilo. Si uno deja de enviar datos durante más de 1 s, su robot simulado se queda quieto
y se pinta de rojo, y los demás siguen funcionando. Cada 2 s se muestra una tabla con el estado de todos.

### Enseñar y reproducir (sobresaliente)

Requisitos en PolyScope: robot encendido (ON → START, estado Normal), *Settings → System → Remote Control* habilitado
y el icono de arriba a la derecha en **Remote**. En Remote la pestaña *Move* está desactivada: para enseñar puntos
moviendo el robot desde PolyScope, pasar a **Local**, guardar los puntos con `punto` y volver a **Remote** antes de
`ejecutar` (los puntos de `deslizadores` se pueden enseñar en Remote).

```bash
python ensenar_reproducir.py                       # robot por defecto de config/robots.json
```

Órdenes (se escriben en la consola): `punto` (guardar la posición actual), `deslizadores` (punto desde PyBullet),
`lista`, `borrar N`, `vaciar`, `ver` (previsualizar con el robot fantasma azul), `ejecutar`, `pausa`, `seguir`,
`cancelar`, `guardar NOMBRE`, `cargar NOMBRE`, `estado`, `ayuda`, `salir`.

Cada punto se envía como `movej(q, a=0.5, v=0.3)` por el socket del puerto 30001 y no se envía el siguiente hasta que
`isProgramRunning` ha pasado a verdadero y luego a falso y `q_actual` está a menos de 0,01 rad del objetivo. Un error del
robot (tipo 20, subtipos 6 o 10) o una parada de protección detienen la secuencia. Las secuencias se guardan en
`secuencias/NOMBRE.json` (radianes).

Para probarlo sin URSim: `python herramientas/robot_falso.py --quieto` acepta `movej`, `stopj` y bloques `def … end`,
y para provocar un error, `falso_parada()` / `falso_rearmar()` (solo en el robot falso).

### Probar en casa sin URSim

```bash
python herramientas/robot_falso.py --trocear          # terminal 1: robot falso (30001 y 30003)
python primaria.py --config config/robot_falso.json   # terminal 2
```

`--trocear` envía los bytes en trozos de tamaño aleatorio para comprobar que el búfer delimita bien los mensajes.
El robot falso **no sustituye** a la validación con URSim: solo emite tramas con el mismo formato.

## Diseño

**Lectura del búfer** (válida para las dos interfaces, `ur_protocolo.BufferTramas`):

1. `recv()` y añadir lo recibido al final de un `bytearray`. Si devuelve 0 bytes, el robot ha cerrado.
2. Mientras haya al menos una cabecera (5 bytes en la primaria, 4 en tiempo real), leer la longitud `L` sin quitarla.
3. Si `L` es imposible (< cabecera o > 64 kB), el búfer está desalineado: cerrar y reconectar.
4. Si hay menos de `L` bytes, esperar al siguiente `recv()`. Si hay `L` o más, cortar el mensaje y quitarlo del búfer.
5. Volver al paso 2: puede haber otro mensaje completo esperando.

**Interfaz primaria:** del mensaje de estado (tipo 16) se recorren los subpaquetes saltando cada uno con su longitud;
del subpaquete 1 (*Joint data*, 251 B) se lee el primer `double` de cada bloque de 41 B (`>dddffffB`).
Los mensajes de tipo 20 (versión, errores, excepciones) se muestran; cualquier otro tipo se salta.

**Interfaz de tiempo real:** paquetes de estructura fija; `q_actual` son 6 `double` a partir del byte 252.
La recepción consume todos los paquetes y guarda solo el último; la ventana se actualiza como mucho 60 veces
por segundo. Así el robot simulado no se queda atrás aunque lleguen 500 paquetes por segundo.

**Robustez** (`ur_conexion.ConexionUR`): `recv()` con timeout de 0,1 s para no bloquear el programa; si el robot cierra,
si el búfer se desalinea o si pasa demasiado tiempo sin datos (2 s en la primaria, 0,5 s en tiempo real: robot
colgado o red caída), se cierra la conexión y se reintenta cada 2 s, sin colgarse.
