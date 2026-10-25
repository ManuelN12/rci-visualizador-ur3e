"""Robot falso: imita las interfaces primaria (30001) y de tiempo real (30003) de un UR3e.

Sirve para desarrollar y probar en casa, sin URSim. NO sustituye a la validación con URSim
ni con el robot real: solo emite tramas con el mismo formato.

Qué envía:
  - Puerto primaria: al conectar, el mensaje de versión (tipo 20, subtipo 3); después, a 10 Hz,
    mensajes de estado (tipo 16) con varios subpaquetes (0, 1, 2, 3, 4, 7 y 8, más uno de un tipo
    no documentado que el cliente debe saltar). Cada 15 s, un mensaje de texto (tipo 20, subtipo 0).
  - Puerto tiempo real: a 500 Hz, paquetes de 1220 bytes con q_actual en el byte 252.

El brazo se mueve solo, despacio, alrededor de una postura fácil de reconocer.
Con --trocear, los bytes se envían en trozos de tamaño aleatorio, como pasaría en una red
cargada: así se comprueba que el búfer del cliente corta bien los mensajes.

Uso:
  python herramientas/robot_falso.py                         # puertos 30001 y 30003
  python herramientas/robot_falso.py --puerto-primaria 31001 --puerto-tiempo-real 31003
  python herramientas/robot_falso.py --trocear
"""
from __future__ import annotations

import argparse
import math
import random
import socket
import struct
import sys
import threading
import time

POSTURA_BASE = [0.0, -math.pi / 2, 0.0, -math.pi / 2, 0.0, 0.0]  # hombro y muñeca 1 a -90°
AMPLITUD = [0.6, 0.3, 0.5, 0.4, 0.6, 1.0]                         # rad
PERIODO_MOVIMIENTO = [12.0, 9.0, 7.0, 11.0, 13.0, 8.0]            # s
LONGITUD_TIEMPO_REAL = 1220                                        # RealTime 5.10


class Brazo:
    """Estado simulado del brazo: los ángulos dependen solo del tiempo."""

    def __init__(self) -> None:
        self.inicio = time.monotonic()

    def tiempo(self) -> float:
        return time.monotonic() - self.inicio

    def q(self) -> list:
        t = self.tiempo()
        return [b + a * math.sin(2 * math.pi * t / p)
                for b, a, p in zip(POSTURA_BASE, AMPLITUD, PERIODO_MOVIMIENTO)]

    def qd(self) -> list:
        t = self.tiempo()
        return [a * 2 * math.pi / p * math.cos(2 * math.pi * t / p)
                for a, p in zip(AMPLITUD, PERIODO_MOVIMIENTO)]


# --------------------------------------------------------------------------- tramas primaria
def subpaquete(tipo: int, contenido: bytes) -> bytes:
    return struct.pack(">iB", 5 + len(contenido), tipo) + contenido


def mensaje(tipo: int, contenido: bytes) -> bytes:
    return struct.pack(">iB", 5 + len(contenido), tipo) + contenido


def mensaje_version() -> bytes:
    proyecto = b"URControl"
    contenido = struct.pack(">Qbb", int(time.time() * 1000), -1, 3)
    contenido += struct.pack(">b", len(proyecto)) + proyecto
    contenido += struct.pack(">BBii", 5, 15, 0, 123456) + b"25-10-2026, 10:00:00"
    return mensaje(20, contenido)


def mensaje_texto(texto: str) -> bytes:
    return mensaje(20, struct.pack(">Qbb", int(time.time() * 1000), -2, 0) + texto.encode())


def mensaje_estado(brazo: Brazo) -> bytes:
    q, qd = brazo.q(), brazo.qd()
    marca = int(brazo.tiempo() * 1e6)
    # 0 · Robot mode data: conectado, habilitado, encendido, sin paradas, sin programa, RUNNING (7)
    modo = struct.pack(">Q???????BBdddB", marca, True, True, True, False, False, False, False,
                       7, 0, 1.0, 1.0, 1.0, 0)
    # 1 · Joint data: un bloque de 41 bytes por articulación
    articulaciones = b"".join(
        struct.pack(">dddffffB", q[j], q[j], qd[j], 0.1, 48.0, 30.0 + j, 35.0, 253) for j in range(6))
    # 4 · Cartesian info: 12 doubles (pose de la herramienta y desplazamiento del TCP), sin calcular
    cartesiano = struct.pack(">12d", *([0.0] * 12))
    cuerpo = (
        subpaquete(0, modo)
        + subpaquete(1, articulaciones)
        + subpaquete(2, bytes(36))            # Tool data (relleno)
        + subpaquete(3, bytes(70))            # Masterboard data (relleno)
        + subpaquete(4, cartesiano)
        + subpaquete(7, bytes(56))            # Force mode data (relleno)
        + subpaquete(8, bytes(4))             # Additional info (relleno)
        + subpaquete(99, bytes(11))           # tipo no documentado: el cliente debe saltarlo
    )
    return mensaje(16, cuerpo)


# --------------------------------------------------------------------------- tramas tiempo real
def paquete_tiempo_real(brazo: Brazo) -> bytes:
    q, qd = brazo.q(), brazo.qd()
    campos = [0.0] * ((LONGITUD_TIEMPO_REAL - 4) // 8)   # 152 doubles después de la longitud
    campos[0] = brazo.tiempo()                            # Time (byte 4)
    campos[1:7] = q                                       # q target (byte 12)
    campos[7:13] = qd                                     # qd target
    campos[31:37] = q                                     # q actual (byte 252)
    campos[37:43] = qd                                    # qd actual (byte 300)
    campos[94] = 7.0                                      # Robot mode (byte 756) = RUNNING
    return struct.pack(">i", LONGITUD_TIEMPO_REAL) + struct.pack(f">{len(campos)}d", *campos)


# --------------------------------------------------------------------------- envío
def enviar(conexion: socket.socket, datos: bytes, trocear: bool) -> None:
    if not trocear:
        conexion.sendall(datos)
        return
    i = 0
    while i < len(datos):
        n = random.randint(1, 700)
        conexion.sendall(datos[i:i + n])
        i += n
        if random.random() < 0.3:
            time.sleep(0.0005)


def atender_primaria(conexion: socket.socket, brazo: Brazo, trocear: bool) -> None:
    enviar(conexion, mensaje_version(), trocear)
    siguiente = time.monotonic()
    proximo_texto = siguiente + 15
    while True:
        enviar(conexion, mensaje_estado(brazo), trocear)
        if time.monotonic() >= proximo_texto:
            enviar(conexion, mensaje_texto("Mensaje de prueba del robot falso"), trocear)
            proximo_texto += 15
        siguiente += 0.1
        time.sleep(max(0.0, siguiente - time.monotonic()))


def atender_tiempo_real(conexion: socket.socket, brazo: Brazo, trocear: bool) -> None:
    siguiente = time.monotonic()
    while True:
        enviar(conexion, paquete_tiempo_real(brazo), trocear)
        siguiente += 0.002                       # 500 Hz
        espera = siguiente - time.monotonic()
        if espera > 0:
            time.sleep(espera)
        # si vamos con retraso no se duerme: se envía el siguiente enseguida


def servidor(nombre: str, ip: str, puerto: int, atender, brazo: Brazo, trocear: bool) -> None:
    escucha = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform != "win32":   # relanzar sin esperar a que el SO libere el puerto (como en la práctica 0)
        escucha.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        escucha.bind((ip, puerto))
    except OSError as exc:
        print(f"{nombre}: no se puede abrir {ip}:{puerto} ({exc}). ¿Hay otro robot falso en marcha?",
              flush=True)
        return
    escucha.listen()
    print(f"{nombre}: escuchando en {ip}:{puerto}", flush=True)
    while True:
        conexion, direccion = escucha.accept()
        print(f"{nombre}: cliente conectado desde {direccion[0]}:{direccion[1]}", flush=True)

        def hilo_cliente(c=conexion, d=direccion):
            try:
                with c:
                    atender(c, brazo, trocear)
            except OSError:
                print(f"{nombre}: el cliente {d[0]}:{d[1]} se ha ido", flush=True)

        threading.Thread(target=hilo_cliente, daemon=True).start()


def main() -> None:
    parser = argparse.ArgumentParser(description="Robot falso con las interfaces del UR3e")
    parser.add_argument("--ip", default="127.0.0.1", help="0.0.0.0 para aceptar conexiones de otros equipos")
    parser.add_argument("--puerto-primaria", type=int, default=30001)
    parser.add_argument("--puerto-tiempo-real", type=int, default=30003)
    parser.add_argument("--trocear", action="store_true", help="enviar en trozos de tamaño aleatorio")
    args = parser.parse_args()

    brazo = Brazo()
    for nombre, puerto, atender in (("primaria", args.puerto_primaria, atender_primaria),
                                    ("tiempo real", args.puerto_tiempo_real, atender_tiempo_real)):
        threading.Thread(target=servidor, args=(nombre, args.ip, puerto, atender, brazo, args.trocear),
                         daemon=True).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nRobot falso detenido.")


if __name__ == "__main__":
    main()
