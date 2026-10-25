"""Conexión TCP con un UR3e: búfer, vigilancia de silencio (watchdog) y reconexión automática.

La clase ConexionUR no se bloquea nunca más de unas décimas de segundo, así el programa
que la usa (la ventana de PyBullet, el bucle principal) sigue vivo aunque el robot se apague.
Cada llamada a leer() hace un ciclo:

  - si no hay conexión, intenta conectar (como mucho una vez cada `espera_reintento` s);
  - si la hay, hace un recv() con timeout, mete los bytes en el búfer y devuelve
    los mensajes completos que haya (puede ser una lista vacía);
  - si el robot cierra la conexión, si el búfer se desalinea o si pasa más de
    `silencio_max` s sin recibir nada (robot colgado, cable cortado), cierra y
    vuelve a empezar.
"""
from __future__ import annotations

import socket
import time
from typing import Callable, List, Optional

from ur_protocolo import BufferTramas, ErrorProtocolo


def registro_consola(nombre: str, texto: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {nombre}: {texto}", flush=True)


class ConexionUR:
    def __init__(self, nombre: str, ip: str, puerto: int, tam_cabecera: int,
                 silencio_max: float = 2.0, espera_reintento: float = 2.0,
                 timeout_conexion: float = 2.0, timeout_recv: float = 0.1,
                 registro: Callable[[str, str], None] = registro_consola) -> None:
        self.nombre = nombre
        self.ip = ip
        self.puerto = puerto
        self.silencio_max = silencio_max
        self.espera_reintento = espera_reintento
        self.timeout_conexion = timeout_conexion
        self.timeout_recv = timeout_recv
        self._registro = registro

        self.buffer = BufferTramas(tam_cabecera)
        self.sock: Optional[socket.socket] = None
        self.ultima_recepcion = 0.0         # time.monotonic() del último recv con datos
        self._ultimo_intento = -espera_reintento
        self.ultimos_recv: List[int] = []   # bytes devueltos por cada recv() del último ciclo
        self.conexiones = 0                 # cuántas veces se ha conectado (para estadísticas)

    # ------------------------------------------------------------------ estado
    @property
    def conectado(self) -> bool:
        return self.sock is not None

    def silencio(self) -> float:
        """Segundos desde que llegó el último byte."""
        return time.monotonic() - self.ultima_recepcion

    def log(self, texto: str) -> None:
        self._registro(self.nombre, texto)

    # ------------------------------------------------------------------ conexión
    def _conectar(self) -> None:
        ahora = time.monotonic()
        if ahora - self._ultimo_intento < self.espera_reintento:
            time.sleep(self.timeout_recv)    # no machacar al robot con intentos: esperar
            return
        self._ultimo_intento = ahora
        try:
            sock = socket.create_connection((self.ip, self.puerto), timeout=self.timeout_conexion)
        except OSError as exc:
            self.log(f"no se puede conectar a {self.ip}:{self.puerto} ({exc}); reintento en "
                     f"{self.espera_reintento:.0f} s")
            return
        sock.settimeout(self.timeout_recv)
        self.sock = sock
        self.buffer.vaciar()                 # nunca mezclar bytes de una conexión anterior
        self.ultima_recepcion = time.monotonic()
        self.conexiones += 1
        local = sock.getsockname()
        self.log(f"conectado a {self.ip}:{self.puerto} desde {local[0]}:{local[1]}")

    def cerrar(self, motivo: str = "") -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None
            if motivo:
                self.log(f"conexión cerrada: {motivo}")
        self.buffer.vaciar()

    # ------------------------------------------------------------------ lectura
    def leer(self) -> List[bytes]:
        """Un ciclo de lectura. Devuelve los mensajes completos recibidos (puede estar vacía)."""
        self.ultimos_recv = []
        if self.sock is None:
            self._conectar()
            return []

        try:
            trozo = self.sock.recv(65536)
        except socket.timeout:
            # No ha llegado nada en timeout_recv: comprobar el watchdog
            if self.silencio() > self.silencio_max:
                self.cerrar(f"sin datos desde hace {self.silencio():.1f} s (robot colgado o red caída)")
            return []
        except OSError as exc:   # ConnectionResetError, ConnectionAbortedError...
            self.cerrar(f"error de red ({exc})")
            return []

        if not trozo:
            self.cerrar("el robot ha cerrado la conexión")
            return []

        self.ultimos_recv.append(len(trozo))
        self.ultima_recepcion = time.monotonic()
        self.buffer.agregar(trozo)
        try:
            return list(self.buffer.mensajes())
        except ErrorProtocolo as exc:
            # Búfer desalineado: lo más seguro es cerrar y volver a conectar
            self.cerrar(f"error de protocolo ({exc})")
            return []

    # ------------------------------------------------------------------ escritura
    def enviar_texto(self, texto: str) -> bool:
        """Envía una línea de texto (URScript). Devuelve False si no hay conexión."""
        if self.sock is None:
            return False
        if not texto.endswith("\n"):
            texto += "\n"   # sin salto de línea el controlador no ejecuta nada
        try:
            self.sock.sendall(texto.encode("utf-8"))
            return True
        except OSError as exc:
            self.cerrar(f"error al enviar ({exc})")
            return False
