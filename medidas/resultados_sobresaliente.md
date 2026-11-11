# Resultados · Sobresaliente (enseñar y reproducir) con URSim

**Fecha:** 11 de noviembre de 2026
**Simulador:** URSim 5.25.2 en VirtualBox (VM 10.164.57.193) · portátil 10.164.51.207 (Wi‑Fi, misma subred /20)
**Script:** `python ensenar_reproducir.py` (entorno conda `ur3e`)

## Preparación en PolyScope

- Robot encendido: ON → START hasta *Robot in Normal Mode* (modo `RUNNING` = 7).
- Icono de arriba a la derecha en **Remote** (*Settings → System → Remote Control* habilitado).
- En Remote, PolyScope **desactiva** las pestañas *Move*, *Program* e *Installation*: el robot solo obedece a la red.
  Para enseñar puntos moviendo el robot a mano hay que pasar a **Local** y volver a **Remote** antes de ejecutar.

Antes de ejecutar, `estado` mostró:

```
conectado=True  último dato hace 0.1 s  modo=RUNNING  programa en marcha=False  parada protección=False  ejecución=INACTIVO
```

## Enseñar

| Punto | Origen | Base | Shoulder | Elbow | Wrist 1 | Wrist 2 | Wrist 3 (°) |
|---|---|---|---|---|---|---|---|
| 1 | PolyScope (*Move*, en Local) | −92,25 | −68,71 | −106,85 | −95,93 | 91,38 | −2,31 |
| 2 | PolyScope | −98,80 | −75,58 | −105,73 | −82,20 | 88,77 | 23,07 |
| 3 | PolyScope | −98,80 | −89,26 | −47,64 | −126,61 | 88,77 | 23,07 |
| 4 | Deslizadores de PyBullet (en Remote) | 45,47 | −144,00 | 0,00 | 0,00 | 0,00 | 0,00 |

`ver` recorrió los 4 puntos con el robot fantasma azul sin enviar nada al robot. La secuencia se guardó con
`guardar demo` (`secuencias/demo.json`) y se recuperó con `cargar demo` tras reiniciar el programa.

## Ejecutar

```
[14:27:41] ▶ Ejecutando secuencia de 4 puntos (v=0.3 rad/s, a=0.5 rad/s²)
[14:27:41] → punto 1/4 enviado: movej a (  -92.25   -68.71  -106.85   -95.93    91.38    -2.31) °
[14:27:48] ✓ punto 1/4 alcanzado (error máx. 0.000°)
[14:27:52] ✓ punto 2/4 alcanzado (error máx. 0.000°)
[14:27:59] ✓ punto 3/4 alcanzado (error máx. 0.000°)
[14:28:13] ✓ punto 4/4 alcanzado (error máx. 0.000°)
[14:28:13] ■ Secuencia completada.
```

- Cada `movej` produce dos *Key messages* (tipo 20, subtipo 7): `PROGRAM_XXX_STARTED` y `PROGRAM_XXX_STOPPED`. El
  siguiente punto solo se envía cuando el programa ha terminado (`isProgramRunning` = falso) **y** `q_actual` está a
  menos de 0,01 rad del objetivo.
- El tramo 3 → 4 (base +144°, 2,51 rad a 0,3 rad/s ≈ 8,4 s teóricos) tardó **14 s**: URSim va al ≈ 60 % del tiempo real
  (8,4 / 0,6 ≈ 14 s), lo mismo que se midió en el bloque B2 con el campo *Time*.
- Error final 0,000° en los 4 puntos: en simulación no hay error de seguimiento.

## Error provocado: apagar el robot a mitad de movimiento

Durante el tramo 3 → 4 se pulsó **OFF** en la pantalla *Initialize* de PolyScope:

```
[14:45:27] → punto 4/4 enviado: movej a (   45.47  -144.00     0.00     0.00     0.00     0.00) °
[14:45:27]   [robot · aviso] PROGRAM_XXX_STARTED movej
[14:45:28]   [robot · aviso] PROGRAM_XXX_PAUSED movej
[14:45:28] ⏸ SECUENCIA DETENIDA en el punto 4/4: el movimiento terminó lejos del objetivo (141.22° de error)
seguir
[14:45:49] ⏸ SECUENCIA DETENIDA en el punto 4/4: el robot no está en marcha (modo POWER_OFF): enciéndelo con ON → START
          (ON → START en PolyScope)
seguir
[14:46:33] → punto 4/4 enviado: movej a (   45.47  -144.00     0.00     0.00     0.00     0.00) °
[14:46:33]   [robot · aviso] PROGRAM_XXX_STOPPED movej
[14:46:33]   [robot · aviso] PROGRAM_XXX_STARTED movej
[14:46:47]   [robot · aviso] PROGRAM_XXX_STOPPED movej
[14:46:48] ✓ punto 4/4 alcanzado (error máx. 0.000°)
[14:46:48] ■ Secuencia completada.
```

1. Al apagar, el controlador **pausa** el programa (`PROGRAM_XXX_PAUSED`) y `isProgramRunning` pasa a falso con el robot
   a 141° del objetivo. El ejecutor no da el punto por alcanzado: **detiene la secuencia**.
2. `seguir` con el robot apagado se **rechaza** sin enviar nada: la comprobación previa ve el modo `POWER_OFF` (3).
3. Tras ON → START, `seguir` reenvía el punto 4. El controlador primero da por terminado el programa pausado
   (`STOPPED`) y arranca el nuevo (`STARTED`); la secuencia termina con normalidad.

**Conclusión:** enviar un `movej` no garantiza que el robot llegue (pregunta 9). El programa cierra el lazo con el estado
que publica el propio robot y no continúa mientras el robot no esté en condiciones de ejecutar.
