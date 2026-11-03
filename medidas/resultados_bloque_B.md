# Resultados · Bloque B (interfaz de tiempo real) con URSim

**Fecha:** 3 de noviembre de 2026
**Simulador:** URSim 5.25.2 (PolyScope 5.25) en VirtualBox, modelo UR3 · VM 10.164.57.193 · portátil 10.164.49.233
**Python:** entorno conda `ur3e` (Python 3.12)

## B1 · Longitud de los paquetes

`python tiempo_real.py --modo paquetes`: **todos los paquetes miden 1220 B**, la longitud de la tabla RealTime 5.10 o
posterior (en 5.9 serían 1140 B). Ningún paquete de otra longitud: el búfer con cabecera de 4 bytes delimita bien.

## B2 · Frecuencia

`python tiempo_real.py --modo frecuencia` (extracto):

```
[11:52:05]  307.0 paquetes/s   recv llenos   0   retraso       —
           reloj robot:  2.00 ms/paquete, 0.61 s por s real
[11:52:06]  318.0 paquetes/s   recv llenos   0   retraso       —
           reloj robot:  2.00 ms/paquete, 0.63 s por s real
[11:52:08]  281.0 paquetes/s   recv llenos   0   retraso       —
           reloj robot:  2.01 ms/paquete, 0.56 s por s real
```

- Llegan **≈ 270–320 paquetes/s**, no 500.
- El campo *Time* (byte 4) avanza **2,00 ms por paquete**: el controlador genera un paquete por ciclo de 500 Hz
  **de su propio reloj**.
- Pero ese reloj avanza solo **0,53–0,63 s por cada segundo real**: URSim, dentro de la VM, no llega a tiempo real.
  300 ≈ 0,6 × 500.
- **recv llenos = 0** en todos los intervalos: ningún `recv()` devolvió el máximo pedido (64 kB), así que el sistema
  operativo nunca tenía datos acumulados. **El programa consume todo lo que llega, sin quedarse atrás.**

**Conclusión:** la frecuencia menor se debe al simulador, no al cliente. Con un UR3e real (controlador a tiempo real)
llegarían 500 paquetes/s.

**Lección sobre la medida del retraso (pregunta 7):** una primera versión estimaba el retraso comparando el reloj del PC
con el campo *Time* del robot, suponiendo que este avanza a tiempo real. Con URSim al 60 % la "edad" calculada crecía
≈ 0,4 s cada segundo aunque el programa iba al día (falso positivo). Se sustituyó por el indicador *recv llenos*, que no
depende del reloj del robot, y la medida por relojes solo se muestra cuando el reloj del robot va a 1 s por s real.
Comparar relojes de dos equipos solo es fiable si ambos avanzan al mismo ritmo y están sincronizados.

## B3 · Ángulos desde el byte 252

`python tiempo_real.py --modo angulos` frente a la pestaña *Move* de PolyScope:

| | Base | Shoulder | Elbow | Wrist 1 | Wrist 2 | Wrist 3 |
|---|---|---|---|---|---|---|
| PolyScope | −28,27 | −90,27 | −0,01 | −90,01 | −75,03 | 0,36 |
| tiempo_real.py | −28,27 | −90,27 | −0,01 | −90,01 | −75,03 | 0,36 |

Coinciden exactamente, igual que con la interfaz primaria, pero sin recorrer subpaquetes: `q_actual` está siempre en el
byte 252 (6 × `double`).

## B4 · Visor sin retraso acumulado

`python tiempo_real.py`: la recepción consume todos los paquetes y guarda solo el último; la ventana se actualiza como
mucho 60 veces por segundo.

```
[12:00:40]  283.4 paquetes/s   recv llenos   0   retraso       —
[12:01:00]  258.4 paquetes/s   recv llenos   0   retraso       —
[12:01:20]  288.4 paquetes/s   recv llenos   0   retraso       —
[12:01:40]  271.2 paquetes/s   recv llenos   0   retraso       —
```

Moviendo el robot rápido en URSim durante más de un minuto, **recv llenos = 0** en todos los intervalos y, al soltar,
**el robot de PyBullet se detiene a la vez que el de URSim**: no hay retraso acumulado.
