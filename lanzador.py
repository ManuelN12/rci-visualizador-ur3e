"""Punto de entrada único para el ejecutable (PyInstaller).

Con doble clic muestra un menú. Desde una consola se le pasan las mismas opciones que a los scripts:

    visualizador_ur3e primaria --modo angulos
    visualizador_ur3e tiempo_real --config config/ur3e_real.json
    visualizador_ur3e varios --config config/dos_ursim.json
    visualizador_ur3e ensenar --config config/ur3e_real.json
    visualizador_ur3e falso --quieto

Cada programa sigue siendo el mismo módulo: aquí solo se elige cuál ejecutar y se le pasan los argumentos.
"""
from __future__ import annotations

import sys

import configuracion

PROGRAMAS = {
    # orden: (módulo, descripción)
    "primaria": ("primaria", "Interfaz primaria, puerto 30001 (aprobado, bloque A)"),
    "tiempo_real": ("tiempo_real", "Interfaz de tiempo real, puerto 30003 (aprobado, bloque B)"),
    "varios": ("varios_robots", "Varios robots en la misma ventana (notable)"),
    "ensenar": ("ensenar_reproducir", "Enseñar y reproducir (sobresaliente)"),
    "falso": ("herramientas.robot_falso", "Robot falso para pruebas sin URSim"),
}


def ejecutar(orden: str, argumentos: list) -> None:
    import importlib

    modulo, _ = PROGRAMAS[orden]
    sys.argv = [f"visualizador_ur3e {orden}"] + argumentos   # argparse de cada script lee sys.argv
    importlib.import_module(modulo).main()


def menu() -> None:
    print("Visualizador de un UR3e por TCP/IP · Redes de Comunicación Industriales")
    print(f"Carpeta: {configuracion.CARPETA_BASE}\n")
    ordenes = list(PROGRAMAS)
    for i, orden in enumerate(ordenes, 1):
        print(f"  {i}. {PROGRAMAS[orden][1]}")
    eleccion = input("\nElige programa [1-5]: ").strip()
    if not eleccion.isdigit() or not 1 <= int(eleccion) <= len(ordenes):
        print("Opción no válida.")
        return
    orden = ordenes[int(eleccion) - 1]

    argumentos = []
    if orden != "falso":
        print("\nFicheros de configuración en config/: robots.json (por defecto), ur3e_real.json, dos_ursim.json…")
        fichero = input("Fichero de configuración (Enter = robots.json): ").strip()
        if fichero:
            if "/" not in fichero and "\\" not in fichero:
                fichero = str(configuracion.CARPETA_BASE / "config" / fichero)
            argumentos += ["--config", fichero]
    extra = input("Opciones adicionales (por ejemplo --modo angulos; Enter = ninguna): ").strip()
    argumentos += extra.split()
    print()
    ejecutar(orden, argumentos)


def main() -> None:
    doble_clic = len(sys.argv) <= 1          # sin argumentos: abierto con doble clic
    try:
        if len(sys.argv) > 1 and sys.argv[1] in PROGRAMAS:
            ejecutar(sys.argv[1], sys.argv[2:])
        elif len(sys.argv) > 1:
            print(__doc__)
        else:
            menu()
    except KeyboardInterrupt:
        pass
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code)
    finally:
        if doble_clic and getattr(sys, "frozen", False):
            input("\nPulsa Enter para cerrar…")   # que la ventana no se cierre sin dejar leer los mensajes


if __name__ == "__main__":
    main()
