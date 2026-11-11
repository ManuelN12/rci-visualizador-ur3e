"""Bloque D · Sobresaliente: mini-aplicación «Enseñar y reproducir».

El ciclo básico de una célula robotizada: enseñar una tarea, comprobarla antes de ejecutarla y
supervisar su ejecución.

  1. ENSEÑAR      Se lleva el robot a una posición (pestaña Move de URSim, o guiado manual en el real) y
                  con «punto» se guarda su configuración actual, leída de la interfaz primaria.
                  También se puede definir un punto con los deslizadores de PyBullet («deslizadores»).
  2. VER          «ver» reproduce la secuencia en PyBullet con un robot «fantasma» (azul, translúcido)
                  antes de mover el robot de verdad.
  3. EJECUTAR     «ejecutar» envía un movej por punto (URScript, texto + \\n, por el mismo socket del 30001)
                  y NO envía el siguiente hasta comprobar con el estado que publica el robot que el anterior
                  ha terminado: isProgramRunning pasa a verdadero (orden aceptada), después a falso (terminada),
                  y q_actual queda a menos de 0,01 rad del objetivo en cada articulación.
  4. SUPERVISAR   Si llega un error (tipo 20, subtipos 6 o 10) o se activa una parada de protección,
                  la secuencia se detiene, se muestra el motivo y se espera a «seguir» o «cancelar».
  5. GUARDAR      «guardar nombre» / «cargar nombre»: la secuencia en secuencias/nombre.json (radianes).

Límites de seguridad (obligatorios en el robot real): v = 0,3 rad/s y a = 0,5 rad/s². Cada ángulo se valida
antes de enviarlo (entre −2π y 2π: un movej interpreta radianes, y 90 serían más de 14 vueltas).

Uso:
  python ensenar_reproducir.py                                  # primer robot de config/robots.json
  python ensenar_reproducir.py --config config/robot_falso.json --robot falso1
"""
from __future__ import annotations

import argparse
import json
import math
import queue
import sys
import threading
import time
from math import degrees
from pathlib import Path
from typing import List, Optional

import configuracion
import ur_protocolo as ur
from receptor import Lectura, ReceptorRobot

V_MAX = 0.3               # rad/s   (límite del enunciado para el robot real)
A_MAX = 0.5               # rad/s²
TOLERANCIA = 0.01         # rad: distancia máxima al objetivo para dar el punto por alcanzado
ESPERA_ARRANQUE = 2.0     # s para que isProgramRunning pase a verdadero tras enviar el movej
MAX_MOVIMIENTO = 120.0    # s: un movimiento que dure más se considera atascado
FRESCURA = 1.0            # s: antigüedad máxima del estado para fiarse de él
FPS = 30
CARPETA_SECUENCIAS = configuracion.CARPETA_BASE / "secuencias"   # junto al .py o junto al .exe
ROBOT_RUNNING = 7

AYUDA = """
Órdenes (escribe y pulsa Enter):
  punto               guardar la posición actual del robot como punto de la secuencia
  deslizadores        guardar un punto con los deslizadores j0..j5 de PyBullet
  lista               ver la secuencia
  borrar N            borrar el punto N            vaciar        borrar todos
  ver                 previsualizar la secuencia en PyBullet (robot fantasma azul)
  ejecutar            ejecutar la secuencia en el robot, punto a punto
  pausa               detener el robot (stopj) y pausar la secuencia
  seguir              reanudar desde el punto en que se detuvo
  cancelar            cancelar la ejecución
  guardar NOMBRE      guardar la secuencia en secuencias/NOMBRE.json
  cargar NOMBRE       cargar una secuencia guardada
  estado              estado del robot          ayuda         esta ayuda          salir
"""


# --------------------------------------------------------------------------- utilidades
def validar_q(q) -> Optional[str]:
    """Devuelve el motivo si q no es una configuración articular segura de enviar, o None si es válida."""
    if not isinstance(q, (list, tuple)) or len(q) != 6:
        return "hacen falta 6 ángulos"
    for i, v in enumerate(q):
        if not isinstance(v, (int, float)) or not math.isfinite(v):
            return f"articulación {i}: valor no numérico"
        if abs(v) > 2 * math.pi:
            return f"articulación {i}: {v:.3f} rad fuera de ±2π (¿grados en vez de radianes?)"
    return None


def orden_movej(q: List[float]) -> str:
    """Texto URScript de un movimiento articular con los límites de seguridad."""
    return f"movej([{', '.join(f'{v:.6f}' for v in q)}], a={A_MAX}, v={V_MAX})"


def grados(q: List[float]) -> str:
    return " ".join(f"{degrees(v):8.2f}" for v in q)


def distancia(a: List[float], b: List[float]) -> float:
    return max(abs(x - y) for x, y in zip(a, b))


def log(texto: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {texto}", flush=True)


# --------------------------------------------------------------------------- ejecución supervisada
class Ejecutor:
    """Máquina de estados que ejecuta la secuencia punto a punto, confirmando cada movimiento.

    INACTIVO ─ejecutar→ (comprobar robot) ─envía movej→ ESPERANDO ─running=1→ MOVIENDO ─running=0→ (¿llegó?)
       ▲                                                   │ 2 s sin arrancar     │ error / parada
       └────────────── cancelar / fin ─────────── PAUSADO ◄┴──────────────────────┘
    """

    def __init__(self, receptor: ReceptorRobot) -> None:
        self.receptor = receptor
        self.estado = "INACTIVO"
        self.puntos: List[List[float]] = []
        self.indice = 0
        self.momento = 0.0           # cuándo se entró en el estado actual
        self.motivo = ""

    @property
    def activo(self) -> bool:
        return self.estado in ("ESPERANDO", "MOVIENDO")

    def _cambiar(self, estado: str) -> None:
        self.estado = estado
        self.momento = time.monotonic()

    def iniciar(self, puntos: List[List[float]], lectura: Lectura) -> None:
        if not puntos:
            log("La secuencia está vacía.")
            return
        self.puntos = [list(p) for p in puntos]
        self.indice = 0
        log(f"▶ Ejecutando secuencia de {len(self.puntos)} puntos (v={V_MAX} rad/s, a={A_MAX} rad/s²)")
        self._enviar_punto(lectura)

    def pausar(self, motivo: str, parar_robot: bool = False) -> None:
        if parar_robot:
            self.receptor.conexion.enviar_texto("stopj(2.0)")
        self.motivo = motivo
        self._cambiar("PAUSADO")
        log(f"⏸ SECUENCIA DETENIDA en el punto {self.indice + 1}/{len(self.puntos)}: {motivo}")
        log("  Escribe «seguir» para reintentar ese punto o «cancelar» para abandonar.")

    def seguir(self, lectura: Lectura) -> None:
        if self.estado != "PAUSADO":
            log("No hay ninguna secuencia pausada.")
            return
        log(f"▶ Reanudando desde el punto {self.indice + 1}")
        self._enviar_punto(lectura)

    def cancelar(self) -> None:
        if self.activo:
            self.receptor.conexion.enviar_texto("stopj(2.0)")
        if self.estado != "INACTIVO":
            log("■ Secuencia cancelada.")
        self._cambiar("INACTIVO")

    def _comprobar_robot(self, lectura: Lectura) -> Optional[str]:
        """Condiciones previas para enviar una orden. Devuelve el motivo si no se cumplen."""
        if not lectura.conectado:
            return "sin conexión con el robot"
        if lectura.modo is None or lectura.edad > FRESCURA:
            return "no llega el estado del robot"
        m = lectura.modo
        if m.parada_emergencia:
            return "parada de emergencia activa"
        if m.parada_proteccion:
            return "parada de protección activa (desbloquéala en PolyScope)"
        if m.modo_robot != ROBOT_RUNNING:
            return f"el robot no está en marcha (modo {m.nombre_modo}): enciéndelo con ON → START"
        if m.programa_en_marcha:
            return "el robot ya está ejecutando un programa"
        return None

    def _enviar_punto(self, lectura: Lectura) -> None:
        objetivo = self.puntos[self.indice]
        problema = validar_q(objetivo) or self._comprobar_robot(lectura)
        if problema:
            self.pausar(problema)
            return
        if not self.receptor.conexion.enviar_texto(orden_movej(objetivo)):
            self.pausar("no se pudo enviar la orden")
            return
        log(f"→ punto {self.indice + 1}/{len(self.puntos)} enviado: movej a ({grados(objetivo)}) °")
        self._cambiar("ESPERANDO")

    def paso(self, lectura: Lectura) -> None:
        """Se llama en cada vuelta del bucle principal con el último estado del robot."""
        if not self.activo:
            return
        # Supervisión: errores del robot y paradas
        for m in lectura.mensajes_robot:
            if m.es_error or m.subtipo == ur.MENSAJE_EXCEPCION_PROGRAMA:
                self.pausar(f"error del robot · {m.nombre}: {m.texto}")
                return
        if lectura.modo and (lectura.modo.parada_proteccion or lectura.modo.parada_emergencia):
            self.pausar("parada de protección o de emergencia")
            return
        if not lectura.conectado:
            self.pausar("se ha perdido la conexión con el robot")
            return

        objetivo = self.puntos[self.indice]
        en_marcha = bool(lectura.modo and lectura.modo.programa_en_marcha)
        transcurrido = time.monotonic() - self.momento

        if self.estado == "ESPERANDO":
            if en_marcha:
                self._cambiar("MOVIENDO")       # orden aceptada: el robot está ejecutándola
            elif transcurrido > ESPERA_ARRANQUE:
                # Un movimiento muy corto puede empezar y terminar entre dos mensajes de estado (10 Hz)
                if lectura.q and distancia(lectura.q, objetivo) <= TOLERANCIA:
                    self._punto_alcanzado(lectura)
                else:
                    self.pausar("el robot no ha aceptado la orden (¿está en modo Local?, ¿control remoto "
                                "desactivado?). Mira los mensajes del robot en PolyScope")
        elif self.estado == "MOVIENDO":
            if not en_marcha:                    # el programa ha terminado: ¿ha llegado?
                if lectura.q and distancia(lectura.q, objetivo) <= TOLERANCIA:
                    self._punto_alcanzado(lectura)
                else:
                    error = distancia(lectura.q, objetivo) if lectura.q else float("nan")
                    self.pausar(f"el movimiento terminó lejos del objetivo ({degrees(error):.2f}° de error)")
            elif transcurrido > MAX_MOVIMIENTO:
                self.pausar("el movimiento tarda demasiado", parar_robot=True)

    def _punto_alcanzado(self, lectura: Lectura) -> None:
        error = distancia(lectura.q, self.puntos[self.indice])
        log(f"✓ punto {self.indice + 1}/{len(self.puntos)} alcanzado (error máx. {degrees(error):.3f}°)")
        self.indice += 1
        if self.indice >= len(self.puntos):
            log("■ Secuencia completada.")
            self._cambiar("INACTIVO")
        else:
            self._enviar_punto(lectura)


# --------------------------------------------------------------------------- previsualización
class Previsualizacion:
    """Recorre la secuencia en el robot fantasma, interpolando en espacio articular."""

    VELOCIDAD = 3 * V_MAX    # rad/s: más rápido que el robot real para no esperar tanto

    def __init__(self, inicio: List[float], puntos: List[List[float]]) -> None:
        self.tramos = list(zip([inicio] + puntos[:-1], puntos))
        self.tramo = 0
        self.t_tramo = time.monotonic()

    def q(self) -> Optional[List[float]]:
        """Posición del fantasma ahora, o None si ya ha terminado."""
        while self.tramo < len(self.tramos):
            a, b = self.tramos[self.tramo]
            duracion = max(distancia(a, b) / self.VELOCIDAD, 0.3)
            f = (time.monotonic() - self.t_tramo) / duracion
            if f < 1:
                return [x + (y - x) * f for x, y in zip(a, b)]
            self.tramo += 1
            self.t_tramo = time.monotonic()
            log(f"  previsualización: punto {self.tramo}/{len(self.tramos)}")
        return None


# --------------------------------------------------------------------------- teclado
def leer_teclado(cola: "queue.Queue[str]") -> None:
    """Hilo aparte: input() bloquea, así que no puede estar en el bucle que dibuja y supervisa."""
    while True:
        try:
            linea = input()
        except EOFError:
            cola.put("salir")
            return
        cola.put(linea.strip())


# --------------------------------------------------------------------------- programa principal
def main() -> None:
    parser = argparse.ArgumentParser(description="Visualizador UR3e · Enseñar y reproducir (sobresaliente)")
    parser.add_argument("--config", help="fichero JSON de robots (por defecto config/robots.json)")
    parser.add_argument("--robot", help="nombre del robot en el fichero (por defecto, el primero)")
    parser.add_argument("--sin-visor", action="store_true", help="no abrir PyBullet")
    args = parser.parse_args()

    cfg = configuracion.cargar(args.config)
    robot = cfg.robot(args.robot)
    receptor = ReceptorRobot(robot, "primaria").start()
    ejecutor = Ejecutor(receptor)
    puntos: List[List[float]] = []
    previa: Optional[Previsualizacion] = None

    visor = id_real = id_fantasma = None
    if not args.sin_visor:
        from visor import Visor
        visor = Visor(cfg.convenio)
        id_real = visor.anadir_robot(robot.pose)
        id_fantasma = visor.anadir_robot(robot.pose)          # mismo sitio, translúcido
        visor.colorear(id_fantasma, [0.2, 0.6, 1.0, 0.35])

    print(f"Enseñar y reproducir · {robot.nombre} · {robot.ip}:{robot.puerto_primaria}")
    print(AYUDA)
    teclado: "queue.Queue[str]" = queue.Queue()
    threading.Thread(target=leer_teclado, args=(teclado,), daemon=True, name="teclado").start()

    lectura = receptor.leer()
    try:
        while True:
            inicio = time.monotonic()
            lectura = receptor.leer()

            # Mensajes del robot: siempre se muestran (y el ejecutor los usa para supervisar)
            for m in lectura.mensajes_robot:
                aviso = "⚠ " if m.es_error or m.subtipo == ur.MENSAJE_EXCEPCION_PROGRAMA else ""
                log(f"  {aviso}[robot · {m.nombre}] {m.texto}")
            ejecutor.paso(lectura)

            # Órdenes del operador
            while not teclado.empty():
                partes = teclado.get().split()
                if not partes:
                    continue
                orden, resto = partes[0].lower(), partes[1:]

                if orden == "salir":
                    raise KeyboardInterrupt
                elif orden == "ayuda":
                    print(AYUDA)
                elif orden == "estado":
                    m = lectura.modo
                    print(f"  conectado={lectura.conectado}  último dato hace {lectura.edad:.1f} s  "
                          f"modo={m.nombre_modo if m else '—'}  programa en marcha={m.programa_en_marcha if m else '—'}  "
                          f"parada protección={m.parada_proteccion if m else '—'}  ejecución={ejecutor.estado}")
                    if lectura.q:
                        print(f"  q_actual (°): {grados(lectura.q)}")
                elif ejecutor.activo and orden not in ("pausa", "cancelar"):
                    log("Ejecutando: solo se admite «pausa» o «cancelar».")
                elif orden == "punto":
                    if lectura.q is None or lectura.edad > FRESCURA:
                        log("No hay un estado reciente del robot: no se puede guardar el punto.")
                    else:
                        puntos.append(list(lectura.q))
                        log(f"Punto {len(puntos)} guardado: ({grados(lectura.q)}) °")
                elif orden == "deslizadores":
                    if not visor:
                        log("Sin visor no hay deslizadores.")
                        continue
                    q = visor.q_deslizadores()
                    problema = validar_q(q)
                    if problema:
                        log(f"Punto no válido: {problema}")
                    else:
                        puntos.append(q)
                        log(f"Punto {len(puntos)} guardado desde los deslizadores: ({grados(q)}) °")
                elif orden == "lista":
                    if not puntos:
                        print("  (secuencia vacía)")
                    for i, p in enumerate(puntos, 1):
                        print(f"  {i:2d}: ({grados(p)}) °")
                elif orden == "borrar" and resto and resto[0].isdigit():
                    n = int(resto[0])
                    if 1 <= n <= len(puntos):
                        puntos.pop(n - 1)
                        log(f"Punto {n} borrado. Quedan {len(puntos)}.")
                    else:
                        log(f"No existe el punto {n}.")
                elif orden == "vaciar":
                    puntos.clear()
                    log("Secuencia vacía.")
                elif orden == "ver":
                    if not visor:
                        log("Sin visor no se puede previsualizar.")
                    elif not puntos:
                        log("La secuencia está vacía.")
                    else:
                        previa = Previsualizacion(lectura.q or puntos[0], puntos)
                        log(f"Previsualizando {len(puntos)} puntos en el robot fantasma (azul)…")
                elif orden == "ejecutar":
                    ejecutor.iniciar(puntos, lectura)
                elif orden == "pausa":
                    if ejecutor.activo:
                        ejecutor.pausar("pausa pedida por el operador", parar_robot=True)
                    else:
                        log("No hay nada en ejecución.")
                elif orden == "seguir":
                    ejecutor.seguir(lectura)
                elif orden == "cancelar":
                    ejecutor.cancelar()
                elif orden == "guardar" and resto:
                    CARPETA_SECUENCIAS.mkdir(exist_ok=True)
                    ruta = CARPETA_SECUENCIAS / f"{resto[0]}.json"
                    with open(ruta, "w", encoding="utf-8") as f:
                        json.dump({"robot": robot.nombre, "unidades": "rad",
                                   "fecha": time.strftime("%Y-%m-%d %H:%M:%S"), "puntos": puntos}, f, indent=2)
                    log(f"Secuencia de {len(puntos)} puntos guardada en {ruta}")
                elif orden == "cargar" and resto:
                    ruta = CARPETA_SECUENCIAS / f"{resto[0]}.json"
                    try:
                        with open(ruta, encoding="utf-8-sig") as f:
                            cargados = json.load(f)["puntos"]
                    except (OSError, ValueError, KeyError) as exc:
                        log(f"No se puede cargar {ruta}: {exc}")
                        continue
                    errores = [f"punto {i}: {validar_q(p)}" for i, p in enumerate(cargados, 1) if validar_q(p)]
                    if errores:
                        log("Secuencia rechazada: " + "; ".join(errores))
                    else:
                        puntos = [list(map(float, p)) for p in cargados]
                        log(f"Cargada {ruta} ({len(puntos)} puntos). Usa «lista» y «ver» antes de «ejecutar».")
                else:
                    log(f"Orden no reconocida: «{' '.join(partes)}». Escribe «ayuda».")

            # Dibujo: el robot real siempre; el fantasma, en la previsualización o en el punto siguiente
            if visor:
                if lectura.q is not None:
                    visor.mover(id_real, lectura.q)
                q_fantasma = previa.q() if previa else None
                if previa and q_fantasma is None:
                    previa = None
                    log("Previsualización terminada.")
                if q_fantasma is None:
                    if ejecutor.activo or ejecutor.estado == "PAUSADO":
                        q_fantasma = ejecutor.puntos[ejecutor.indice]   # adónde va el robot
                    elif puntos:
                        q_fantasma = puntos[-1]                          # último punto enseñado
                    else:
                        q_fantasma = lectura.q
                if q_fantasma is not None:
                    visor.mover(id_fantasma, q_fantasma)

            time.sleep(max(0.0, 1 / FPS - (time.monotonic() - inicio)))
    except KeyboardInterrupt:
        print("\nSaliendo…")
    finally:
        if ejecutor.activo:
            ejecutor.cancelar()
        receptor.detener()


if __name__ == "__main__":
    main()
