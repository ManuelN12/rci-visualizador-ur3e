"""Bloque A · Visualizador con la interfaz primaria del UR3e (puerto 30001, 10 Hz).

Lee los mensajes del robot, los delimita con un búfer usando su longitud, recorre los
subpaquetes del mensaje de estado (tipo 16), extrae los 6 q_actual del subpaquete 1 y
mueve con ellos el UR3e de PyBullet.

Cada hito del enunciado tiene su modo, para comprobarlo por separado:
  --modo bytes        A1 · cuántos bytes devuelve cada recv()
  --modo mensajes     A2 · longitud y tipo de cada mensaje completo
  --modo subpaquetes  A3 · tipo y tamaño de cada subpaquete; comprueba que suman L - 5
  --modo angulos      A4 · los 6 q_actual en grados
  --modo visor        A5 · mueve el robot de PyBullet (por defecto)

Ejemplos:
  python primaria.py --modo bytes --registro medidas/recv_primaria.csv
  python primaria.py                                  # robot por defecto de config/robots.json
  python primaria.py --config config/robot_falso.json # contra el robot falso
"""
from __future__ import annotations

import argparse
import csv
import time
from math import degrees

import configuracion
import ur_protocolo as ur
from ur_conexion import ConexionUR

SILENCIO_MAX = 2.0   # s sin datos (20 mensajes perdidos a 10 Hz) -> robot colgado: reconectar


def formatear_grados(q) -> str:
    return "  ".join(f"{degrees(v):8.2f}" for v in q)


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualizador UR3e · interfaz primaria (30001)")
    parser.add_argument("--config", help="fichero JSON de robots (por defecto config/robots.json)")
    parser.add_argument("--robot", help="nombre del robot en el fichero (por defecto, el primero)")
    parser.add_argument("--modo", default="visor",
                        choices=["bytes", "mensajes", "subpaquetes", "angulos", "visor"])
    parser.add_argument("--registro", help="modo bytes: guardar en CSV la hora y los bytes de cada recv()")
    args = parser.parse_args()

    cfg = configuracion.cargar(args.config)
    robot = cfg.robot(args.robot)
    conexion = ConexionUR(robot.nombre, robot.ip, robot.puerto_primaria,
                          tam_cabecera=ur.CABECERA_PRIMARIA.size, silencio_max=SILENCIO_MAX)

    visor = id_visor = None
    if args.modo == "visor":
        from visor import Visor          # solo se importa PyBullet si hace falta
        visor = Visor(cfg.convenio)
        id_visor = visor.anadir_robot(robot.pose)

    registro = None
    if args.registro:
        fichero_registro = open(args.registro, "w", newline="", encoding="utf-8")
        registro = csv.writer(fichero_registro)
        registro.writerow(["t_s", "bytes_recv"])
    t0 = time.monotonic()

    print(f"Interfaz primaria · {robot.nombre} · {robot.ip}:{robot.puerto_primaria} · modo {args.modo}")
    print("Ctrl + C para salir.\n")

    mensajes_estado = 0
    ultimo_informe = time.monotonic()
    try:
        while True:
            mensajes = conexion.leer()

            # A1 · bytes por recv(): no tienen por qué coincidir con un mensaje
            if args.modo == "bytes":
                for n in conexion.ultimos_recv:
                    print(f"recv() devolvió {n:6d} B   (quedan {len(conexion.buffer):5d} B en el búfer)")
                    if registro:
                        registro.writerow([f"{time.monotonic() - t0:.4f}", n])

            for msg in mensajes:
                tipo = ur.tipo_mensaje(msg)

                if args.modo == "mensajes":
                    print(f"mensaje: longitud {len(msg):5d} B   tipo {tipo}")

                # Mensajes del robot (tipo 20): versión, errores, textos. Se muestran siempre.
                if tipo == ur.MENSAJE_ROBOT:
                    m = ur.decodificar_mensaje_robot(msg)
                    if args.modo != "bytes":
                        aviso = "⚠ " if m.es_error or m.subtipo == ur.MENSAJE_EXCEPCION_PROGRAMA else ""
                        print(f"  {aviso}[robot · {m.nombre}] {m.texto}")
                    continue

                if tipo != ur.MENSAJE_ESTADO_ROBOT:
                    continue          # otros tipos (25, internos...): se ignoran

                estado = ur.decodificar_estado(msg)
                mensajes_estado += 1
                for aviso in estado.avisos:
                    print(f"  ⚠ {aviso}")

                if args.modo == "subpaquetes":
                    suma = sum(tam for _, tam in estado.subpaquetes)
                    correcto = "✓" if suma == len(msg) - 5 else "✗"
                    lista = ", ".join(f"{t}:{tam}" for t, tam in estado.subpaquetes)
                    print(f"estado {len(msg)} B → subpaquetes (tipo:tamaño) {lista}"
                          f"   suma {suma} = {len(msg)} - 5 {correcto}")

                elif args.modo == "angulos" and estado.q_actual:
                    print(f"q_actual (°): {formatear_grados(estado.q_actual)}")

                elif args.modo == "visor" and estado.q_actual:
                    visor.mover(id_visor, estado.q_actual)

            # En modo visor, una línea de estado cada 5 s para saber que todo va bien
            transcurrido = time.monotonic() - ultimo_informe
            if args.modo == "visor" and transcurrido >= 5.0:
                ultimo_informe = time.monotonic()
                if conexion.conectado:
                    print(f"[{time.strftime('%H:%M:%S')}] {mensajes_estado / transcurrido:4.1f} "
                          "mensajes de estado/s", flush=True)
                mensajes_estado = 0
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
    finally:
        conexion.cerrar()
        if registro:
            fichero_registro.close()
            print(f"Registro guardado en {args.registro}")


if __name__ == "__main__":
    main()
