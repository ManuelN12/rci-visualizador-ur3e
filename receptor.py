"""Hilo receptor de un robot: recibe en segundo plano y guarda el último estado.

Es la clase ReceptorHora de la práctica 1 (ejemplo 2), aplicada al UR3e:

  - Cada robot tiene su hilo, su socket y su búfer (dentro de ConexionUR). El hilo pasa casi
    todo el tiempo bloqueado en recv(), pero eso solo le afecta a él: los demás robots y la
    ventana siguen funcionando.
  - El hilo solo ESCRIBE el último estado decodificado; el hilo principal solo lo LEE con leer().
  - El estado compartido se protege con un threading.Lock. Dentro de la sección crítica no se
    espera a nada: solo se copian o asignan valores.
  - Si el robot se cuelga, se apaga o se desconecta, ConexionUR lo detecta (watchdog / recv = 0)
    y reintenta la conexión; mientras tanto el hilo principal ve que el dato envejece.

Sirve para las dos interfaces:
  interfaz="primaria"     puerto 30001, 10 Hz: ángulos + modo del robot + mensajes del robot
  interfaz="tiempo_real"  puerto 30003, 500 Hz: ángulos (byte 252)
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional

import ur_protocolo as ur
from configuracion import ConfigRobot
from ur_conexion import ConexionUR

SILENCIO_MAX = {"primaria": 2.0, "tiempo_real": 0.5}   # s sin datos -> cerrar y reconectar


@dataclass
class Lectura:
    """Copia del estado de un robot en un instante (la devuelve leer())."""
    nombre: str
    conectado: bool
    q: Optional[List[float]]              # últimos q_actual (rad), None si aún no ha llegado ninguno
    edad: float                           # s desde que llegó ese q (inf si nunca)
    modo: Optional[ur.ModoRobot]          # solo interfaz primaria
    mensajes_por_s: float
    mensajes_robot: List[ur.MensajeRobot] = field(default_factory=list)  # nuevos desde la última lectura


class ReceptorRobot:
    def __init__(self, robot: ConfigRobot, interfaz: str = "primaria") -> None:
        if interfaz not in SILENCIO_MAX:
            raise ValueError(f"interfaz desconocida: {interfaz}")
        self.robot = robot
        self.interfaz = interfaz
        puerto = robot.puerto_primaria if interfaz == "primaria" else robot.puerto_tiempo_real
        cabecera = ur.CABECERA_PRIMARIA.size if interfaz == "primaria" else ur.CABECERA_TIEMPO_REAL.size
        self.conexion = ConexionUR(robot.nombre, robot.ip, puerto, tam_cabecera=cabecera,
                                   silencio_max=SILENCIO_MAX[interfaz])

        # Estado compartido entre el hilo receptor y el principal: solo se toca con el candado cogido.
        self._candado = threading.Lock()
        self._q: Optional[List[float]] = None
        self._momento_q = 0.0
        self._modo: Optional[ur.ModoRobot] = None
        self._conectado = False
        self._mensajes_robot: deque = deque(maxlen=50)
        self._contador = 0
        self._ritmo = 0.0

        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._recibir, name=f"receptor-{robot.nombre}", daemon=True)

    # ------------------------------------------------------------------ hilo principal
    def start(self) -> "ReceptorRobot":
        self._hilo.start()
        return self

    def detener(self) -> None:
        self._parar.set()
        self._hilo.join(timeout=2)
        self.conexion.cerrar()

    def leer(self) -> Lectura:
        """Devuelve una copia coherente del último estado (lo llama el hilo principal)."""
        with self._candado:
            nuevos = list(self._mensajes_robot)
            self._mensajes_robot.clear()
            return Lectura(
                nombre=self.robot.nombre,
                conectado=self._conectado,
                q=list(self._q) if self._q is not None else None,
                edad=(time.monotonic() - self._momento_q) if self._q is not None else float("inf"),
                modo=self._modo,
                mensajes_por_s=self._ritmo,
                mensajes_robot=nuevos,
            )

    # ------------------------------------------------------------------ hilo receptor
    def _recibir(self) -> None:
        """Cuerpo del hilo: lee sin parar y guarda el último estado."""
        inicio_ritmo = time.monotonic()
        while not self._parar.is_set():
            mensajes = self.conexion.leer()          # recv con timeout: nunca se bloquea mucho
            q = modo = None
            n_q = 0                                   # mensajes con ángulos en este ciclo
            nuevos_mensajes = []
            for msg in mensajes:
                if self.interfaz == "tiempo_real":
                    q = ur.tiempo_real_q_actual(msg)
                    n_q += 1
                    continue
                tipo = ur.tipo_mensaje(msg)
                if tipo == ur.MENSAJE_ESTADO_ROBOT:
                    estado = ur.decodificar_estado(msg)
                    if estado.q_actual is not None:
                        q = estado.q_actual
                        n_q += 1
                    if estado.modo is not None:
                        modo = estado.modo
                elif tipo == ur.MENSAJE_ROBOT:
                    nuevos_mensajes.append(ur.decodificar_mensaje_robot(msg))

            ahora = time.monotonic()
            with self._candado:                       # sección crítica: solo asignaciones
                self._conectado = self.conexion.conectado
                if q is not None:
                    self._q = q
                    self._momento_q = ahora
                    self._contador += n_q
                if modo is not None:
                    self._modo = modo
                self._mensajes_robot.extend(nuevos_mensajes)
                if ahora - inicio_ritmo >= 1.0:
                    self._ritmo = self._contador / (ahora - inicio_ritmo)
                    self._contador = 0
                    inicio_ritmo = ahora
