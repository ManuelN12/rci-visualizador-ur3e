# Resultados · Bloque A (interfaz primaria) con URSim

**Fecha:** 3 de noviembre de 2026
**Simulador:** URSim 5.25.2.130406 (PolyScope 5.25) en VirtualBox 7.2.22, modelo UR3, adaptador puente
**Red:** portátil 10.164.49.233 (Wi‑Fi) · VM 10.164.57.193 · máscara /20 (10.164.48.0 – 10.164.63.255)

## A0 · Conectividad

- `ping 10.164.57.193`: 4/4 respuestas, < 1 ms, **TTL = 64** (equipo Linux: la VM).
- `Test-NetConnection -Port 30001` y `-Port 30003`: `TcpTestSucceeded : True`.
- Portátil y VM tienen el tercer octeto distinto (49 y 57) pero están en la misma red porque la máscara es /20.

En el aula (30/10) la VM obtuvo 10.172.18.178 en la red del aula (PC del puesto 10.172.18.175), con el mismo resultado.
Al importar la VM venía en **NAT** y hubo que cambiarla a **Adaptador puente** (pregunta 5).

## A2 · Mensajes de la interfaz primaria

| Tipo | Longitud | Qué es |
|---|---|---|
| 16 | **722 B** (a veces **743 B**) | Robot State Message, 10 Hz |
| 5 | 9 B | No documentado en la práctica (información Modbus según las librerías de UR): se ignora saltándolo por su longitud |

## A3 · Subpaquetes del mensaje de estado (tipo 16)

```
estado 722 B → subpaquetes (tipo:tamaño) 0:47, 1:251, 4:101, 9:53, 3:75, 2:37, 7:61, 8:9, 10:43, 11:26, 12:8, 15:6
suma 717 = 722 - 5 ✓
```

- Joint data (tipo 1) mide **251 B** = 5 + 6 × 41, como predice el enunciado (`>dddffffB`).
- Los mensajes de 743 B llevan un subpaquete extra de 21 B que también se salta sin problema.
- Todas las líneas con ✓: el recorrido por longitudes no se desalinea.

## A4 · Ángulos q_actual frente a PolyScope (pestaña Move)

| | Base | Shoulder | Elbow | Wrist 1 | Wrist 2 | Wrist 3 |
|---|---|---|---|---|---|---|
| PolyScope | −97,42 | −36,16 | −122,47 | −112,98 | 97,57 | 19,64 |
| primaria.py | −97,42 | −36,16 | −122,47 | −112,98 | 97,57 | 19,64 |

Coinciden exactamente.

**Diferencia observada:** en otra postura, PolyScope mostraba Wrist 3 = **358,22°** con la marca **−1R** (una vuelta en
negativo), mientras que por la red llegaba **−1,78°**. Es el mismo ángulo (−1,78 + 360 = 358,22): PolyScope muestra el
ángulo entre 0 y 360° más el número de vueltas, y la interfaz envía el valor real acumulado (las articulaciones del UR
giran ±360°).

## A5 · Visualizador PyBullet

- Entorno: Miniforge (conda-forge) con Python 3.12, `pybullet` 3.25 y el paquete `ur3e_rg2` instalado desde el `.whl`.
  (En Windows no hay `pybullet` precompilado para `pip` con Python reciente; conda-forge sí lo ofrece.)
- `python primaria.py`: el robot de PyBullet sigue al de URSim al moverlo desde la pestaña *Move* (10 mensajes de estado/s).

**Convenio de ángulos:** con URSim en *Home* (0°, −90°, 0°, −90°, 0°, 0°) el robot de PyBullet adopta exactamente la misma
postura vertical, y al mover Base y Wrist 2 los dos giran en el mismo sentido. El modelo URDF usa el mismo origen y
sentido que el controlador: **no hace falta corrección** (`signo` = 1 y `desfase_grados` = 0 en las 6 articulaciones).
