"""Decodificación de los mensajes binarios del UR3e (interfaces primaria y de tiempo real).

Este módulo no abre conexiones: solo convierte bytes en datos. Así se puede probar sin robot
y lo reutilizan todos los scripts (aprobado, notable y sobresaliente).

Fuentes:
  - Primary/Secondary Client Interface (UR, software 5.9 / 5.10), secciones 2 y 3.
  - Realtime Client Interface (UR), tablas RealTime 5.9 / 5.10.

Todo viaja en big-endian: todos los formatos de struct empiezan por ">".
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Iterator, List, Optional

# --------------------------------------------------------------------------- constantes
# Interfaz primaria: cada mensaje empieza con int32 longitud + uint8 tipo (5 bytes).
CABECERA_PRIMARIA = struct.Struct(">iB")
# Interfaz de tiempo real: solo int32 longitud (4 bytes), no hay tipo.
CABECERA_TIEMPO_REAL = struct.Struct(">i")

LONGITUD_MAXIMA = 64 * 1024  # una longitud mayor indica que el búfer está desalineado

# Tipos de mensaje de la interfaz primaria (messageType)
MENSAJE_ESTADO_ROBOT = 16      # Robot State Message: llega a 10 Hz
MENSAJE_ROBOT = 20             # Robot Messages: versión, errores, textos...
MENSAJE_VARIABLES_GLOBALES = 25

# Subpaquetes del mensaje de estado (packageType)
SUBPAQUETE_MODO_ROBOT = 0      # Robot mode data
SUBPAQUETE_ARTICULACIONES = 1  # Joint data
SUBPAQUETE_CARTESIANO = 4      # Cartesian info

# Subtipos de los mensajes de tipo 20 (robotMessageType)
MENSAJE_TEXTO = 0
MENSAJE_POPUP = 2
MENSAJE_VERSION = 3
MENSAJE_MODO_SEGURIDAD = 5
MENSAJE_CODIGO_ERROR = 6       # Robot Comm Message
MENSAJE_EXCEPCION_PROGRAMA = 10  # Runtime Exception Message

# Robot mode data: tras la cabecera de 5 bytes
#   uint64 timestamp, 7 bool, uint8 robotMode, uint8 controlMode,
#   double targetSpeedFraction, double speedScaling, double targetSpeedFractionLimit, uint8 reservado
FORMATO_MODO_ROBOT = struct.Struct(">Q???????BBdddB")   # 42 bytes -> subpaquete de 47

# Joint data: 6 bloques, uno por articulación
#   double q_actual, q_target, qd_actual; float I_actual, V_actual, T_motor, T_micro; uint8 jointMode
FORMATO_ARTICULACION = struct.Struct(">dddffffB")      # 41 bytes
NUM_ARTICULACIONES = 6
TAM_SUBPAQUETE_ARTICULACIONES = 5 + NUM_ARTICULACIONES * FORMATO_ARTICULACION.size  # 251

# Robot Messages (tipo 20): tras la cabecera, uint64 timestamp + int8 source + int8 robotMessageType
FORMATO_CABECERA_MENSAJE_ROBOT = struct.Struct(">Qbb")  # 10 bytes, empieza en el byte 5

# Interfaz de tiempo real: posiciones fijas (desplazamiento en bytes desde el inicio del paquete)
TR_DESPLAZAMIENTO_TIEMPO = 4
TR_DESPLAZAMIENTO_Q_ACTUAL = 252
TR_DESPLAZAMIENTO_MODO_ROBOT = 756   # columna 95 de la tabla (double)
FORMATO_6_DOUBLES = struct.Struct(">6d")

NOMBRES_MODO_ROBOT = {
    -1: "NO_CONTROLLER", 0: "DISCONNECTED", 1: "CONFIRM_SAFETY", 2: "BOOTING",
    3: "POWER_OFF", 4: "POWER_ON", 5: "IDLE", 6: "BACKDRIVE", 7: "RUNNING",
    8: "UPDATING_FIRMWARE",
}


class ErrorProtocolo(Exception):
    """Los bytes no cuadran con el protocolo: búfer desalineado o mensaje corrupto."""


# --------------------------------------------------------------------------- búfer
class BufferTramas:
    """Acumula los bytes que llegan por TCP y corta los mensajes completos.

    TCP entrega un flujo de bytes: un recv() puede traer medio mensaje, uno entero o
    uno y medio. El búfer guarda lo recibido y solo entrega mensajes completos,
    usando la longitud que cada mensaje lleva en sus primeros 4 bytes.

    tam_cabecera = 5 para la interfaz primaria (longitud + tipo)
                 = 4 para la de tiempo real (solo longitud)
    """

    def __init__(self, tam_cabecera: int) -> None:
        self.tam_cabecera = tam_cabecera
        self._datos = bytearray()

    def agregar(self, trozo: bytes) -> None:
        """Paso 1 del algoritmo: añadir al final lo que ha devuelto recv()."""
        self._datos.extend(trozo)

    def mensajes(self) -> Iterator[bytes]:
        """Devuelve, uno a uno, todos los mensajes completos que haya en el búfer."""
        # Paso 2: mientras haya al menos una cabecera, mirar la longitud sin quitarla
        while len(self._datos) >= self.tam_cabecera:
            (longitud,) = CABECERA_TIEMPO_REAL.unpack_from(self._datos, 0)
            if longitud < self.tam_cabecera or longitud > LONGITUD_MAXIMA:
                raise ErrorProtocolo(f"longitud imposible ({longitud} B): búfer desalineado")
            # Paso 3: si el mensaje no ha llegado entero, esperar al siguiente recv()
            if len(self._datos) < longitud:
                return
            # Paso 4: cortar el mensaje y quitarlo del búfer
            mensaje = bytes(self._datos[:longitud])
            del self._datos[:longitud]
            yield mensaje  # paso 5: quien lo use decide qué hacer según su tipo

    def vaciar(self) -> None:
        self._datos.clear()

    def __len__(self) -> int:
        return len(self._datos)


# --------------------------------------------------------------------------- interfaz primaria
@dataclass
class ModoRobot:
    """Lo útil del subpaquete 0 (Robot mode data)."""
    timestamp: int
    robot_conectado: bool
    robot_habilitado: bool
    encendido: bool
    parada_emergencia: bool
    parada_proteccion: bool
    programa_en_marcha: bool
    programa_pausado: bool
    modo_robot: int
    modo_control: int
    escala_velocidad: float

    @property
    def nombre_modo(self) -> str:
        return NOMBRES_MODO_ROBOT.get(self.modo_robot, f"desconocido({self.modo_robot})")


@dataclass
class EstadoRobot:
    """Resultado de decodificar un mensaje de estado (tipo 16)."""
    q_actual: Optional[List[float]] = None          # radianes, 6 valores
    modo: Optional[ModoRobot] = None
    subpaquetes: List[tuple] = field(default_factory=list)  # [(tipo, tamaño), ...]
    avisos: List[str] = field(default_factory=list)


@dataclass
class MensajeRobot:
    """Resultado de decodificar un mensaje de tipo 20."""
    subtipo: int
    texto: str = ""
    es_error: bool = False

    @property
    def nombre(self) -> str:
        return {
            MENSAJE_TEXTO: "texto", MENSAJE_POPUP: "ventana emergente", MENSAJE_VERSION: "versión",
            MENSAJE_MODO_SEGURIDAD: "modo de seguridad", MENSAJE_CODIGO_ERROR: "código de error",
            MENSAJE_EXCEPCION_PROGRAMA: "excepción de programa",
        }.get(self.subtipo, f"subtipo {self.subtipo}")


def tipo_mensaje(mensaje: bytes) -> int:
    """Byte 4 de un mensaje de la interfaz primaria."""
    return mensaje[4]


def recorrer_subpaquetes(mensaje: bytes) -> Iterator[tuple]:
    """Recorre los subpaquetes de un mensaje de estado: devuelve (tipo, inicio, tamaño).

    Misma idea que el búfer, a pequeña escala: cada subpaquete dice cuánto mide,
    así que se puede saltar cualquiera sin saber qué contiene.
    """
    longitud = len(mensaje)
    posicion = CABECERA_PRIMARIA.size  # saltar la cabecera del mensaje (5 bytes)
    while posicion < longitud:
        if posicion + CABECERA_PRIMARIA.size > longitud:
            raise ErrorProtocolo(f"cabecera de subpaquete cortada en el byte {posicion}")
        tam, tipo = CABECERA_PRIMARIA.unpack_from(mensaje, posicion)
        if tam < CABECERA_PRIMARIA.size or posicion + tam > longitud:
            raise ErrorProtocolo(f"subpaquete de tipo {tipo} con tamaño {tam} se sale del mensaje")
        yield tipo, posicion, tam
        posicion += tam  # saltar al siguiente subpaquete


def decodificar_articulaciones(mensaje: bytes, inicio: int) -> List[float]:
    """Subpaquete 1: los 6 q_actual (rad). El primero de cada bloque de 41 bytes."""
    q = []
    for j in range(NUM_ARTICULACIONES):
        inicio_art = inicio + CABECERA_PRIMARIA.size + j * FORMATO_ARTICULACION.size
        (q_actual,) = struct.unpack_from(">d", mensaje, inicio_art)
        q.append(q_actual)
    return q


def decodificar_modo_robot(mensaje: bytes, inicio: int) -> ModoRobot:
    """Subpaquete 0: estado general del robot (si está en marcha un programa, paradas...)."""
    campos = FORMATO_MODO_ROBOT.unpack_from(mensaje, inicio + CABECERA_PRIMARIA.size)
    return ModoRobot(
        timestamp=campos[0],
        robot_conectado=campos[1], robot_habilitado=campos[2], encendido=campos[3],
        parada_emergencia=campos[4], parada_proteccion=campos[5],
        programa_en_marcha=campos[6], programa_pausado=campos[7],
        modo_robot=campos[8], modo_control=campos[9], escala_velocidad=campos[11],
    )


def decodificar_estado(mensaje: bytes) -> EstadoRobot:
    """Mensaje de tipo 16: recorre los subpaquetes y extrae los que interesan."""
    estado = EstadoRobot()
    for tipo, inicio, tam in recorrer_subpaquetes(mensaje):
        estado.subpaquetes.append((tipo, tam))
        if tipo == SUBPAQUETE_ARTICULACIONES:
            if tam != TAM_SUBPAQUETE_ARTICULACIONES:
                estado.avisos.append(f"Joint data mide {tam} B y no {TAM_SUBPAQUETE_ARTICULACIONES}: "
                                     "¿otra versión del protocolo?")
            if tam >= TAM_SUBPAQUETE_ARTICULACIONES:
                estado.q_actual = decodificar_articulaciones(mensaje, inicio)
        elif tipo == SUBPAQUETE_MODO_ROBOT and tam >= CABECERA_PRIMARIA.size + FORMATO_MODO_ROBOT.size:
            estado.modo = decodificar_modo_robot(mensaje, inicio)
        # cualquier otro subpaquete se salta: no hace falta saber qué contiene
    return estado


def _texto(datos: bytes) -> str:
    return datos.decode("utf-8", errors="replace").strip("\x00").strip()


def decodificar_mensaje_robot(mensaje: bytes) -> MensajeRobot:
    """Mensaje de tipo 20: versión, errores y textos que publica el controlador."""
    _, _, subtipo = FORMATO_CABECERA_MENSAJE_ROBOT.unpack_from(mensaje, CABECERA_PRIMARIA.size)
    cuerpo = CABECERA_PRIMARIA.size + FORMATO_CABECERA_MENSAJE_ROBOT.size  # byte 15

    if subtipo == MENSAJE_VERSION:
        # int8 projectNameSize, projectName, uint8 major, uint8 minor, int32 bugfix, int32 build, buildDate
        n = mensaje[cuerpo]
        proyecto = _texto(mensaje[cuerpo + 1: cuerpo + 1 + n])
        mayor, menor, correccion, compilacion = struct.unpack_from(">BBii", mensaje, cuerpo + 1 + n)
        return MensajeRobot(subtipo, f"{proyecto} {mayor}.{menor}.{correccion}.{compilacion}")

    if subtipo == MENSAJE_CODIGO_ERROR:
        # int32 código, int32 argumento, int32 nivel, uint32 tipoDato, uint32 dato, texto
        codigo, argumento, nivel = struct.unpack_from(">iii", mensaje, cuerpo)
        texto = _texto(mensaje[cuerpo + 20:])
        # Niveles: 1 INFO, 2 WARNING, 3 VIOLATION, 4 FAULT (128+ son de desarrollo)
        nivel_base = nivel % 128
        return MensajeRobot(subtipo, f"C{codigo}A{argumento} (nivel {nivel}) {texto}", es_error=nivel_base >= 3)

    if subtipo == MENSAJE_EXCEPCION_PROGRAMA:
        linea, columna = struct.unpack_from(">ii", mensaje, cuerpo)
        texto = _texto(mensaje[cuerpo + 8:])
        return MensajeRobot(subtipo, f"línea {linea}, columna {columna}: {texto}", es_error=True)

    if subtipo == MENSAJE_TEXTO:
        return MensajeRobot(subtipo, _texto(mensaje[cuerpo:]))

    if subtipo == MENSAJE_MODO_SEGURIDAD:
        codigo, argumento, modo = struct.unpack_from(">iiB", mensaje, cuerpo)
        return MensajeRobot(subtipo, f"modo de seguridad {modo} (C{codigo}A{argumento})")

    return MensajeRobot(subtipo)  # otros subtipos: se identifican pero no se interpretan


# --------------------------------------------------------------------------- interfaz de tiempo real
def tiempo_real_tiempo(paquete: bytes) -> float:
    """Segundos desde que arrancó el controlador (byte 4)."""
    (t,) = struct.unpack_from(">d", paquete, TR_DESPLAZAMIENTO_TIEMPO)
    return t


def tiempo_real_q_actual(paquete: bytes) -> List[float]:
    """Los 6 q_actual (rad) en posición fija: byte 252."""
    if len(paquete) < TR_DESPLAZAMIENTO_Q_ACTUAL + FORMATO_6_DOUBLES.size:
        raise ErrorProtocolo(f"paquete de tiempo real demasiado corto ({len(paquete)} B)")
    return list(FORMATO_6_DOUBLES.unpack_from(paquete, TR_DESPLAZAMIENTO_Q_ACTUAL))


def tiempo_real_modo_robot(paquete: bytes) -> Optional[int]:
    """Robot mode (viaja como double) si el paquete es lo bastante largo."""
    if len(paquete) < TR_DESPLAZAMIENTO_MODO_ROBOT + 8:
        return None
    (modo,) = struct.unpack_from(">d", paquete, TR_DESPLAZAMIENTO_MODO_ROBOT)
    return int(modo)
