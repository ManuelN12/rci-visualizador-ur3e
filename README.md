# Visualizador de un UR3e por TCP/IP

**Asignatura:** Redes de Comunicación Industriales · Máster en Electrónica Industrial · Universidad de Deusto
**Alumno:** Manuel Narváez
**Curso:** 2026–2027

Programa en Python que se conecta por TCP/IP a un robot UR3e (real o simulado con URSim), decodifica byte a byte
los mensajes binarios que emite y reproduce su configuración articular en el simulador PyBullet.

## Estado

| Nivel | Requisitos | Estado |
|---|---|---|
| Aprobado (5) | `primaria.py` (30001) y `tiempo_real.py` (30003), con búfer y delimitación por longitud | ✅ Probado con el robot falso · ⏳ pendiente de validar con URSim |
| Notable (7) | Varios robots en la misma ventana, configurados por fichero, uno por hilo | ⏳ |
| Sobresaliente (10) | Envío de órdenes URScript y mini-aplicación «Enseñar y reproducir» | ⏳ |

## Estructura

```
├── primaria.py            Bloque A · interfaz primaria (puerto 30001, 10 Hz)
├── tiempo_real.py         Bloque B · interfaz de tiempo real (puerto 30003, 500 Hz)
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
        { "nombre": "ursim", "ip": "10.172.18.100", "puerto_primaria": 30001, "puerto_tiempo_real": 30003,
          "pose": [0, 0, 0, 0, 0, 0] }
    ],
    "convenio_angulos": { "signo": [1, 1, 1, 1, 1, 1], "desfase_grados": [0, 0, 0, 0, 0, 0] }
}
```

- `pose`: posición de la base del robot simulado en la escena: `[x, y, z]` en metros y `[roll, pitch, yaw]` en radianes.
- `convenio_angulos`: corrección si alguna articulación del modelo de PyBullet tuviera otro origen o sentido
  (`q_modelo = signo · q_ur + desfase`).
- Otro fichero: `--config ruta.json`. Otro robot de la lista: `--robot nombre`.

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
| B2 | `python tiempo_real.py --modo frecuencia` | Unos 500 paquetes por segundo y retraso estable |
| B3 | `python tiempo_real.py --modo angulos` | Coinciden con los de `primaria.py` |
| B4 | `python tiempo_real.py` | Tras mover rápido el robot, el simulado no acumula retraso |

Para la pregunta 1 de la memoria: `python primaria.py --modo bytes --registro medidas/recv_primaria.csv`
guarda en CSV la hora y los bytes de cada `recv()`.

Ctrl + C para salir.

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
