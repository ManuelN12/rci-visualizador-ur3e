"""Robot falso: imita las interfaces primaria (30001) y de tiempo real (30003) de un UR3e.

Sirve para desarrollar y probar en casa, sin URSim. NO sustituye a la validación con URSim
ni con el robot real: solo emite tramas con el mismo formato.

Qué envía:
  - Puerto primaria: al conectar, el mensaje de versión (tipo 20, subtipo 3); después, a 10 Hz,
    mensajes de estado (tipo 16) con varios subpaquetes (0, 1, 2, 3, 4, 7 y 8, más uno de un tipo
    no documentado que el cliente debe saltar). Cada 15 s, un mensaje de texto (tipo 20, subtipo 0).
  - Puerto tiempo real: a 500 Hz, paquetes de 1220 bytes con q_actual en el byte 252.

El brazo se mueve solo, despacio, alrededor de una postura fácil de reconocer, hasta que recibe la
primera orden (o desde el principio está quieto, con --quieto).
Con --trocear, los bytes se envían en trozos de tamaño aleatorio, como pasaría en una red
cargada: así se comprueba que el búfer del cliente corta bien los mensajes.

Órdenes (URScript en texto, terminado en \n, por el puerto primaria), para probar el sobresaliente:
  movej([q0, ..., q5], a=..., v=...)   movimiento articular: isProgramRunning = True mientras se mueve
  def nombre(): ... end                 varias órdenes movej seguidas (un programa)
  stopj(a)                              detiene el movimiento
  falso_parada()                        SOLO PRUEBAS: simula una parada de protección
  falso_rearmar()                       SOLO PRUEBAS: la quita (como "desbloquear" en PolyScope)
  falso_local() / falso_remoto()        SOLO PRUEBAS: pasa el robot a Local / Remote
Como el UR3e real, el permiso de cada conexión se fija al conectar: una conexión abierta con el robot
en Local es de solo lectura (sus órdenes se rechazan con el error C210A0) aunque luego se pase a Remote.
Un programa nuevo aborta el que esté en marcha. Ángulos fuera de ±2π, o un programa enviado durante
una parada de protección, se rechazan con un mensaje de error (tipo 20), como haría el robot.

Uso:
  python herramientas/robot_falso.py                         # puertos 30001 y 30003
  python herramientas/robot_falso.py --puerto-primaria 31001 --puerto-tiempo-real 31003
  python herramientas/robot_falso.py --trocear
  python herramientas/robot_falso.py --quieto                # brazo parado en Home hasta recibir órdenes
  python herramientas/robot_falso.py --quieto --local        # empieza en Local (prueba del error C210)
"""
from __future__ import annotations

import argparse
import math
import queue
import random
import re
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
    """Estado simulado del brazo.

    Modo libre: los ángulos dependen solo del tiempo (el brazo "baila" solo).
    Modo órdenes: el brazo está quieto y solo se mueve con movej, a velocidad articular v.
    """

    def __init__(self, quieto: bool = False, remoto: bool = True) -> None:
        self.inicio = time.monotonic()
        self._candado = threading.Lock()
        self._libre = not quieto
        self._q = list(POSTURA_BASE)
        self._qd = [0.0] * 6
        self._objetivos = []            # movej pendientes: [(q, v), ...]
        self.programa_en_marcha = False
        self.parada_proteccion = False
        self.remoto = remoto            # Remote: las conexiones abiertas ahora pueden dar órdenes
        self._inicio_programa = 0.0
        self._suscriptores = []         # una cola de mensajes (tipo 20) por cliente de la primaria
        threading.Thread(target=self._mover, name="brazo", daemon=True).start()

    def tiempo(self) -> float:
        return time.monotonic() - self.inicio

    def q(self) -> list:
        with self._candado:
            if self._libre:
                t = self.tiempo()
                return [b + a * math.sin(2 * math.pi * t / p)
                        for b, a, p in zip(POSTURA_BASE, AMPLITUD, PERIODO_MOVIMIENTO)]
            return list(self._q)

    def qd(self) -> list:
        with self._candado:
            if self._libre:
                t = self.tiempo()
                return [a * 2 * math.pi / p * math.cos(2 * math.pi * t / p)
                        for a, p in zip(AMPLITUD, PERIODO_MOVIMIENTO)]
            return list(self._qd)

    # ------------------------------------------------------------------ mensajes del robot
    def suscribir(self) -> "queue.Queue":
        cola = queue.Queue()
        with self._candado:
            self._suscriptores.append(cola)
        return cola

    def desuscribir(self, cola: "queue.Queue") -> None:
        with self._candado:
            if cola in self._suscriptores:
                self._suscriptores.remove(cola)

    def _publicar(self, datos: bytes) -> None:
        for cola in self._suscriptores:
            cola.put(datos)

    # ------------------------------------------------------------------ órdenes
    def ejecutar(self, programa: str, escritura: bool = True) -> None:
        """Recibe un programa URScript (una línea o un bloque def ... end).

        escritura: si la conexión por la que llega se abrió con el robot en Remote.
        """
        texto = programa.strip()
        print(f"  orden recibida: {texto[:90]}{'…' if len(texto) > 90 else ''}", flush=True)
        with self._candado:
            if "falso_remoto()" in texto or "falso_local()" in texto:
                self.remoto = "falso_remoto()" in texto
                print(f"  robot en {'Remote' if self.remoto else 'Local'}", flush=True)
                return
            if not escritura:
                self._publicar(mensaje_error(1, "", codigo=210, argumento=0))   # como el UR3e real
                print("  rechazada: conexión abierta en Local (solo lectura) → C210A0", flush=True)
                return
            if "falso_parada()" in texto:
                self._parar_movimiento()
                self.parada_proteccion = True
                self._publicar(mensaje_error(3, "C153A1 Protective Stop (simulada en el robot falso)"))
                return
            if "falso_rearmar()" in texto:
                self.parada_proteccion = False
                return
            if texto.startswith("stopj"):
                self._parar_movimiento()
                return
            if self.parada_proteccion:
                self._publicar(mensaje_error(3, "C210A0 No se puede iniciar el programa: parada de protección"))
                return
            objetivos = []
            for m in re.finditer(r"movej\(\s*\[([^\]]*)\]\s*(?:,\s*a\s*=\s*([-\d.eE]+))?"
                                 r"\s*(?:,\s*v\s*=\s*([-\d.eE]+))?", texto):
                try:
                    q = [float(x) for x in m.group(1).split(",")]
                    v = float(m.group(3)) if m.group(3) else 1.05
                except ValueError:
                    q, v = [], 0
                if len(q) != 6 or any(abs(x) > 2 * math.pi for x in q) or v <= 0:
                    self._publicar(mensaje_excepcion(1, 1, "movej: ángulos o velocidad no válidos"))
                    return
                objetivos.append((q, v))
            if not objetivos:
                self._publicar(mensaje_excepcion(1, 1, f"compile_error: orden no reconocida '{texto[:40]}'"))
                return
            if self._libre:                      # primera orden: el brazo se queda donde está
                t = self.tiempo()
                self._q = [b + a * math.sin(2 * math.pi * t / p)
                           for b, a, p in zip(POSTURA_BASE, AMPLITUD, PERIODO_MOVIMIENTO)]
                self._libre = False
            self._objetivos = objetivos          # un programa nuevo aborta el anterior
            self.programa_en_marcha = True
            self._inicio_programa = time.monotonic()

    def _parar_movimiento(self) -> None:
        self._objetivos = []
        self._qd = [0.0] * 6
        self.programa_en_marcha = False

    def _mover(self) -> None:
        """Hilo del brazo: avanza hacia el objetivo actual a 100 Hz (movimiento articular sincronizado)."""
        dt = 0.01
        while True:
            time.sleep(dt)
            with self._candado:
                if not self._objetivos:
                    if self.programa_en_marcha and time.monotonic() - self._inicio_programa > 0.3:
                        self.programa_en_marcha = False
                    continue
                objetivo, v = self._objetivos[0]
                dif = [o - q for o, q in zip(objetivo, self._q)]
                mayor = max(abs(d) for d in dif)
                paso = v * dt
                if mayor <= paso:                 # llegado: siguiente objetivo
                    self._q = list(objetivo)
                    self._qd = [0.0] * 6
                    self._objetivos.pop(0)
                else:                             # todas las articulaciones llegan a la vez
                    factor = paso / mayor
                    self._q = [q + d * factor for q, d in zip(self._q, dif)]
                    self._qd = [d * factor / dt for d in dif]


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


def mensaje_error(nivel: int, texto: str, codigo: int = 0, argumento: int = 0) -> bytes:
    """Robot Comm Message (tipo 20, subtipo 6): código, argumento, nivel, tipo de dato, dato, texto."""
    return mensaje(20, struct.pack(">Qbb", int(time.time() * 1000), -2, 6)
                   + struct.pack(">iiiII", codigo, argumento, nivel, 0, 0) + texto.encode())


def mensaje_excepcion(linea: int, columna: int, texto: str) -> bytes:
    """Runtime Exception Message (tipo 20, subtipo 10)."""
    return mensaje(20, struct.pack(">Qbb", int(time.time() * 1000), -2, 10)
                   + struct.pack(">ii", linea, columna) + texto.encode())


def mensaje_estado(brazo: Brazo) -> bytes:
    q, qd = brazo.q(), brazo.qd()
    marca = int(brazo.tiempo() * 1e6)
    # 0 · Robot mode data: conectado, habilitado, encendido, sin paradas, sin programa, RUNNING (7)
    modo = struct.pack(">Q???????BBdddB", marca, True, True, True, False, brazo.parada_proteccion,
                       brazo.programa_en_marcha, False, 7, 0, 1.0, 1.0, 1.0, 0)
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


def leer_ordenes(conexion: socket.socket, brazo: Brazo, escritura: bool = True) -> None:
    """Hilo por cliente: lee texto URScript línea a línea (un bloque def ... end es un solo programa)."""
    pendiente = b""
    bloque = None
    try:
        while True:
            datos = conexion.recv(4096)
            if not datos:
                return
            pendiente += datos
            while b"\n" in pendiente:
                linea, pendiente = pendiente.split(b"\n", 1)
                texto = linea.decode("utf-8", errors="replace").rstrip()
                if bloque is not None:
                    bloque.append(texto)
                    if texto.strip() == "end":
                        brazo.ejecutar("\n".join(bloque), escritura)
                        bloque = None
                elif texto.strip().startswith("def "):
                    bloque = [texto]
                elif texto.strip():
                    brazo.ejecutar(texto, escritura)
    except OSError:
        return


def atender_primaria(conexion: socket.socket, brazo: Brazo, trocear: bool) -> None:
    mensajes = brazo.suscribir()
    escritura = brazo.remoto       # el permiso se fija al conectar, como en el robot real
    threading.Thread(target=leer_ordenes, args=(conexion, brazo, escritura), daemon=True).start()
    try:
        _emitir_primaria(conexion, brazo, mensajes, trocear)
    finally:
        brazo.desuscribir(mensajes)


def _emitir_primaria(conexion: socket.socket, brazo: Brazo, mensajes: "queue.Queue", trocear: bool) -> None:
    enviar(conexion, mensaje_version(), trocear)
    siguiente = time.monotonic()
    proximo_texto = siguiente + 15
    while True:
        enviar(conexion, mensaje_estado(brazo), trocear)
        while not mensajes.empty():
            enviar(conexion, mensajes.get(), trocear)
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
    parser.add_argument("--quieto", action="store_true", help="brazo quieto en Home hasta recibir órdenes")
    parser.add_argument("--local", action="store_true", help="empezar en Local (las conexiones serán de solo lectura)")
    args = parser.parse_args()

    brazo = Brazo(quieto=args.quieto, remoto=not args.local)
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
