"""Bloque C · Notable: visualiza varios robots a la vez en la misma ventana de PyBullet.

Arquitectura (la recomendada por el enunciado):

    hilo receptor-robot1  ── recv, búfer, decodifica ──┐
    hilo receptor-robot2  ── recv, búfer, decodifica ──┤  último q de cada robot (con Lock)
    ...                                                │
    hilo principal ◄── lee el estado a ritmo fijo ─────┘  y es el ÚNICO que llama a PyBullet

  - Cada robot tiene su hilo, su socket y su búfer (receptor.ReceptorRobot). Si un robot se cuelga
    o se apaga, su hilo se queda esperando o reconectando, pero los demás siguen.
  - La lista de robots (IP, puertos y posición en la escena) se lee del fichero de configuración:
    no se toca el código.
  - Watchdog: si un robot lleva más de WATCHDOG s sin datos, su robot simulado se queda quieto,
    se pinta de rojo y se avisa por consola. Cuando vuelven los datos, recupera su color.

Uso:
  python varios_robots.py --config config/robots.json
  python varios_robots.py --config config/robots.json --interfaz tiempo_real
  python varios_robots.py --config config/robots.json --robots ursim companero
  python varios_robots.py --config config/robots.json --sin-visor      (sin PyBullet: solo consola)
"""
from __future__ import annotations

import argparse
import time
from math import degrees

import configuracion
from receptor import ReceptorRobot

FPS = 30                 # actualizaciones de la ventana por segundo
WATCHDOG = 1.0           # s sin datos nuevos para considerar que un robot no responde
INFORME = 2.0            # s entre tablas de estado en la consola


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualizador UR3e · varios robots (notable)")
    parser.add_argument("--config", help="fichero JSON de robots (por defecto config/robots.json)")
    parser.add_argument("--robots", nargs="+", help="nombres de los robots a usar (por defecto, todos)")
    parser.add_argument("--interfaz", default="primaria", choices=["primaria", "tiempo_real"])
    parser.add_argument("--sin-visor", action="store_true", help="no abrir PyBullet: solo la tabla de estado")
    args = parser.parse_args()

    cfg = configuracion.cargar(args.config)
    robots = [cfg.robot(n) for n in args.robots] if args.robots else cfg.robots

    visor = None
    if not args.sin_visor:
        from visor import Visor
        visor = Visor(cfg.convenio)

    # Un receptor (con su hilo) y un robot simulado por cada robot real
    receptores = []
    ids = {}
    for robot in robots:
        receptores.append(ReceptorRobot(robot, args.interfaz).start())
        if visor:
            ids[robot.nombre] = visor.anadir_robot(robot.pose)
        puerto = robot.puerto_primaria if args.interfaz == "primaria" else robot.puerto_tiempo_real
        print(f"· {robot.nombre:<12} {robot.ip}:{puerto}   pose {robot.pose}")
    print(f"\n{len(receptores)} robots · interfaz {args.interfaz} · Ctrl + C para salir.\n")

    # Al principio ningún robot ha enviado nada: empiezan "sin datos" (en rojo) sin dar el aviso
    sin_datos = {r.robot.nombre: True for r in receptores}
    ultimo_informe = 0.0
    try:
        while True:
            inicio = time.monotonic()
            lecturas = [r.leer() for r in receptores]       # copias: a partir de aquí no hay candados

            for lec in lecturas:
                parado = lec.edad > WATCHDOG
                # Avisar solo cuando cambia el estado, no en cada vuelta
                if parado != sin_datos[lec.nombre]:
                    sin_datos[lec.nombre] = parado
                    if parado:
                        motivo = "desconectado" if not lec.conectado else "conectado pero sin datos"
                        print(f"[{time.strftime('%H:%M:%S')}] ⚠ {lec.nombre}: SIN DATOS ({motivo}); "
                              "su robot simulado se queda quieto y en rojo")
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] ✓ {lec.nombre}: recibiendo datos")
                for m in lec.mensajes_robot:
                    aviso = "⚠ " if m.es_error else ""
                    print(f"  {aviso}[{lec.nombre} · {m.nombre}] {m.texto}")

                if visor:
                    if lec.q is not None and not parado:
                        visor.mover(ids[lec.nombre], lec.q)
                    visor.marcar_sin_datos(ids[lec.nombre], parado)

            # Tabla de estado cada INFORME segundos
            if inicio - ultimo_informe >= INFORME:
                ultimo_informe = inicio
                print(f"--- {time.strftime('%H:%M:%S')} ---")
                for lec in lecturas:
                    estado = "SIN DATOS" if sin_datos[lec.nombre] else "OK"
                    edad = "   —  " if lec.q is None else f"{lec.edad:5.1f} s"
                    angulos = "" if lec.q is None else "  q(°) " + " ".join(f"{degrees(v):7.1f}" for v in lec.q)
                    modo = f"  {lec.modo.nombre_modo}" if lec.modo else ""
                    print(f"  {lec.nombre:<12} {estado:<10} {lec.mensajes_por_s:6.1f} msg/s   "
                          f"último dato hace {edad}{modo}{angulos}")

            # Ritmo fijo de dibujo
            time.sleep(max(0.0, 1 / FPS - (time.monotonic() - inicio)))
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
    finally:
        for r in receptores:
            r.detener()


if __name__ == "__main__":
    main()
