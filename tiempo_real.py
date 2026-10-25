"""Bloque B · Visualizador con la interfaz de tiempo real del UR3e (puerto 30003, 500 Hz).

Mismo búfer que la primaria, pero con cabecera de 4 bytes (no hay tipo) y paquetes de
estructura fija: q_actual está siempre en el byte 252.

Llegan unos 500 paquetes por segundo. Dibujar cada uno haría que la ventana se quedara
atrás, así que se separa la recepción (se consumen todos los paquetes y se guarda solo
el último) del dibujo (como mucho FPS veces por segundo).

  --modo bytes       B1 · cuántos bytes devuelve cada recv()
  --modo paquetes    B1 · longitud de cada paquete (resumen por segundo)
  --modo frecuencia  B2 · paquetes por segundo y retraso acumulado
  --modo angulos     B3 · los 6 q_actual en grados (10 veces por segundo)
  --modo visor       B4 · mueve el robot de PyBullet (por defecto)

El "retraso" compara el reloj del controlador (campo Time, byte 4) con el del PC: si el
programa va más lento que el robot, crece sin parar (los datos envejecen en el búfer).
"""
from __future__ import annotations

import argparse
import csv
import time
from collections import Counter
from math import degrees

import configuracion
import ur_protocolo as ur
from ur_conexion import ConexionUR

SILENCIO_MAX = 0.5   # s sin datos a 500 Hz (250 paquetes perdidos) -> reconectar
FPS = 60             # actualizaciones de la ventana por segundo


class MedidorRetraso:
    """Estima cuánto retraso acumula el programa respecto al robot.

    desfase = hora del PC al procesar el paquete − hora del controlador en el paquete.
    El valor absoluto no significa nada (son dos relojes distintos), pero el menor desfase
    visto corresponde a un paquete procesado "al día". La diferencia con él es el retraso.
    """

    def __init__(self) -> None:
        self.minimo = None

    def reiniciar(self) -> None:
        self.minimo = None

    def medir(self, t_robot: float) -> float:
        desfase = time.monotonic() - t_robot
        if self.minimo is None or desfase < self.minimo:
            self.minimo = desfase
        return desfase - self.minimo


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualizador UR3e · interfaz de tiempo real (30003)")
    parser.add_argument("--config", help="fichero JSON de robots (por defecto config/robots.json)")
    parser.add_argument("--robot", help="nombre del robot en el fichero (por defecto, el primero)")
    parser.add_argument("--modo", default="visor",
                        choices=["bytes", "paquetes", "frecuencia", "angulos", "visor"])
    parser.add_argument("--registro", help="modo bytes: guardar en CSV la hora y los bytes de cada recv()")
    args = parser.parse_args()

    cfg = configuracion.cargar(args.config)
    robot = cfg.robot(args.robot)
    conexion = ConexionUR(robot.nombre, robot.ip, robot.puerto_tiempo_real,
                          tam_cabecera=ur.CABECERA_TIEMPO_REAL.size, silencio_max=SILENCIO_MAX)

    visor = id_visor = None
    if args.modo == "visor":
        from visor import Visor
        visor = Visor(cfg.convenio)
        id_visor = visor.anadir_robot(robot.pose)

    registro = None
    if args.registro:
        fichero_registro = open(args.registro, "w", newline="", encoding="utf-8")
        registro = csv.writer(fichero_registro)
        registro.writerow(["t_s", "bytes_recv"])
    t0 = time.monotonic()

    print(f"Interfaz de tiempo real · {robot.nombre} · {robot.ip}:{robot.puerto_tiempo_real} · modo {args.modo}")
    print("Ctrl + C para salir.\n")

    retraso = MedidorRetraso()
    conexiones_vistas = 0
    ultimo_q = None          # último q_actual recibido (solo se dibuja el último)
    ultimo_dibujo = 0.0
    ultimo_angulos = 0.0
    ultimo_informe = time.monotonic()
    paquetes = 0
    longitudes = Counter()
    retraso_actual = 0.0
    try:
        while True:
            mensajes = conexion.leer()

            if conexion.conexiones != conexiones_vistas:   # nueva conexión: el reloj del robot puede haber cambiado
                conexiones_vistas = conexion.conexiones
                retraso.reiniciar()

            if args.modo == "bytes":
                for n in conexion.ultimos_recv:
                    print(f"recv() devolvió {n:6d} B   = {n / 1220:6.2f} paquetes de 1220 B   "
                          f"(quedan {len(conexion.buffer):5d} B en el búfer)")
                    if registro:
                        registro.writerow([f"{time.monotonic() - t0:.4f}", n])

            # Recepción: consumir TODOS los paquetes, quedarse con el último
            for paquete in mensajes:
                paquetes += 1
                longitudes[len(paquete)] += 1
                ultimo_q = ur.tiempo_real_q_actual(paquete)
                retraso_actual = retraso.medir(ur.tiempo_real_tiempo(paquete))

            ahora = time.monotonic()

            # Dibujo: como mucho FPS veces por segundo, con el último estado
            if args.modo == "visor" and ultimo_q is not None and ahora - ultimo_dibujo >= 1 / FPS:
                visor.mover(id_visor, ultimo_q)
                ultimo_dibujo = ahora

            if args.modo == "angulos" and ultimo_q is not None and ahora - ultimo_angulos >= 0.1:
                print("q_actual (°): " + "  ".join(f"{degrees(v):8.2f}" for v in ultimo_q))
                ultimo_angulos = ahora

            # Resumen por segundo (cada 5 s en modo visor)
            intervalo = 5.0 if args.modo == "visor" else 1.0
            transcurrido = ahora - ultimo_informe
            if transcurrido >= intervalo and args.modo in ("paquetes", "frecuencia", "visor"):
                if conexion.conectado:
                    if args.modo == "paquetes":
                        detalle = ", ".join(f"{n} de {lon} B" for lon, n in sorted(longitudes.items()))
                        print(f"[{time.strftime('%H:%M:%S')}] {paquetes} paquetes: {detalle}")
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] {paquetes / transcurrido:6.1f} paquetes/s   "
                              f"retraso {retraso_actual * 1000:7.1f} ms   "
                              f"búfer {len(conexion.buffer):5d} B", flush=True)
                paquetes = 0
                longitudes.clear()
                ultimo_informe = ahora
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
    finally:
        conexion.cerrar()
        if registro:
            fichero_registro.close()
            print(f"Registro guardado en {args.registro}")


if __name__ == "__main__":
    main()
