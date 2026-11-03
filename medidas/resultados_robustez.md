# Resultados · Robustez frente a caídas del robot (requisito del aprobado)

**Fecha:** 3 de noviembre de 2026 · `python tiempo_real.py` (visor) contra URSim 5.25.2 en VirtualBox

## 1 · Cerrar la interfaz gráfica (PolyScope)

Al cerrar la ventana de PolyScope los paquetes **siguieron llegando**, y más rápido (de ≈ 270 a ≈ 430 paquetes/s):

```
[12:05:30]  253.8 paquetes/s   recv llenos   0   retraso       —
[12:05:35]  430.2 paquetes/s   recv llenos   0   retraso       —
[12:05:40]  448.0 paquetes/s   recv llenos   0   retraso       —
```

- PolyScope es solo la interfaz de usuario. El **controlador** (URControl), que sirve los puertos 30001–30003, es un
  proceso independiente y sigue funcionando (en un robot real: la consola de mando frente al armario de control).
- La interfaz gráfica consumía buena parte de la CPU de la VM: sin ella el controlador se acerca al tiempo real
  (≈ 430 de 500 paquetes/s). Confirma que la frecuencia baja del bloque B2 se debía a los recursos de la VM.

## 2 · Reinicio brusco de la VM (como un corte de corriente)

```
[12:08:20]  440.2 paquetes/s   recv llenos   0   retraso       —
[12:08:23] ursim: conexión cerrada: sin datos desde hace 0.6 s (robot colgado o red caída)
[12:08:25] ursim: no se puede conectar a 10.164.57.193:30003 (timed out); reintento en 2 s
[12:08:27] ursim: no se puede conectar a 10.164.57.193:30003 (timed out); reintento en 2 s
...
```

- No llega ningún aviso de cierre (FIN): lo detecta el **watchdog** al superar 0,5 s sin datos.
- `timed out`: en esa IP no responde nadie (la VM está arrancando). Si el equipo estuviera encendido pero sin el servicio,
  el error sería `Connection refused` (respuesta inmediata del SO). Diagnóstico por capas: *timeout* → red o equipo
  (capas 1–3); *refused* → servicio (capa 4).
- El programa **no se bloquea**: reintenta cada 2 s y la ventana de PyBullet sigue respondiendo.

## 3 · Reinicio ordenado del controlador y reconexión

```
[12:10:31]  188.0 paquetes/s   recv llenos   0   retraso       —
[12:10:32] ursim: conexión cerrada: el robot ha cerrado la conexión
[12:10:34] ursim: no se puede conectar a 10.164.57.193:30003 (timed out); reintento en 2 s
[12:10:35] ursim: conectado a 10.164.57.193:30003 desde 10.164.49.233:54517
[12:10:41]  186.2 paquetes/s   recv llenos   0   retraso       —
```

- Al abrir URSim UR3, su script reinicia el controlador, que cierra la conexión de forma ordenada (`recv` devuelve 0 bytes).
- **El programa se reconecta solo** (12:10:35) y el robot de PyBullet vuelve a seguir al de URSim.

**Conclusión:** el programa sobrevive a caídas abruptas y ordenadas del robot sin colgarse y se reconecta automáticamente.

## 4 · Reconexión con el brazo apagado

Tras el reinicio, el programa se reconectó **antes** de pulsar ON y START en PolyScope (robot en *Power off*). El
controlador abre los puertos 30001–30003 en cuanto arranca, aunque el brazo esté apagado, y sigue publicando el estado
(modo del robot `POWER_OFF` = 3). ON y START solo alimentan los motores y liberan los frenos (`IDLE` = 5 → `RUNNING` = 7).
**Comunicar con el robot no requiere que el brazo esté en marcha**; el modo del robot se usará en el sobresaliente para
comprobar que puede ejecutar órdenes antes de enviarlas.
