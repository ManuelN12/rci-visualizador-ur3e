"""Envoltorio del visualizador PyBullet (paquete UR3e_rg2).

Se encarga de los detalles del módulo proporcionado que el enunciado avisa:
  - move_robot() necesita una lista, no una tupla;
  - move_robot() modifica la lista que recibe (le añade 6 valores): se pasa una copia;
  - el identificador de los robots añadidos lo devuelve spawn_robot() y no es consecutivo;
  - el convenio de ángulos (signo y desfase) se aplica aquí, nunca dentro del módulo.

PyBullet solo debe llamarse desde el hilo principal.
"""
from __future__ import annotations

from typing import List

from configuracion import ConvenioAngulos

ORIGEN = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


class Visor:
    def __init__(self, convenio: ConvenioAngulos) -> None:
        try:
            from UR3e_rg2.dynamic_ur3e import UR3eRG2
        except ImportError as exc:
            raise SystemExit(
                "No se encuentra el visualizador UR3e_rg2. ¿Está activado el entorno virtual y "
                "instalado el .whl? (pip install ur3e_rg2-0.1.0-py3-none-any.whl)\n"
                f"Detalle: {exc}"
            )
        self.convenio = convenio
        self._ur = UR3eRG2()           # abre la ventana y crea el robot 0 en el origen
        self._robot_inicial_usado = False
        self._colores = {}             # robot_id -> [(link, color original)] para poder restaurarlo
        self._marcados = set()         # robots pintados como "sin datos"

    def anadir_robot(self, pose: List[float]) -> int:
        """Devuelve el identificador del robot simulado que seguirá a un robot real.

        El primero reutiliza el robot 0 que crea UR3eRG2() (se recoloca si su pose no es el
        origen); los demás se crean con spawn_robot().
        """
        if not self._robot_inicial_usado:
            self._robot_inicial_usado = True
            if list(pose) != ORIGEN:
                import pybullet as p
                p.resetBasePositionAndOrientation(0, pose[:3], p.getQuaternionFromEuler(pose[3:]))
            return 0
        return self._ur.spawn_robot(list(pose))

    def mover(self, robot_id: int, q_ur: List[float]) -> None:
        """Coloca el robot simulado en los ángulos q_ur (rad) leídos del robot real."""
        q_modelo = self.convenio.aplicar(q_ur)
        self._ur.move_robot(robot_id, list(q_modelo))   # copia: move_robot la modifica

    def marcar_sin_datos(self, robot_id: int, sin_datos: bool) -> None:
        """Pinta de rojo un robot que no recibe datos, o le devuelve su color original."""
        if sin_datos == (robot_id in self._marcados):
            return                                    # ya está como se pide: no repetir llamadas
        import pybullet as p
        if robot_id not in self._colores:
            # getVisualShapeData: una entrada por pieza; [1] = índice del link, [7] = color RGBA
            self._colores[robot_id] = [(d[1], d[7]) for d in p.getVisualShapeData(robot_id)]
        for link, color in self._colores[robot_id]:
            p.changeVisualShape(robot_id, link, rgbaColor=[0.9, 0.15, 0.15, 1] if sin_datos else color)
        if sin_datos:
            self._marcados.add(robot_id)
        else:
            self._marcados.discard(robot_id)

    def colorear(self, robot_id: int, rgba: List[float]) -> None:
        """Pinta todas las piezas de un robot de un color (con transparencia en rgba[3])."""
        import pybullet as p
        for d in p.getVisualShapeData(robot_id):
            p.changeVisualShape(robot_id, d[1], rgbaColor=list(rgba))

    def deslizadores(self) -> dict:
        """Valores de los deslizadores de la ventana (claves ' j0' a ' j11')."""
        return self._ur.get_param_values()

    def q_deslizadores(self) -> List[float]:
        """Los 6 primeros deslizadores (brazo) en radianes, en el convenio del UR."""
        valores = self.deslizadores()
        q_modelo = [valores[f" j{i}"] for i in range(6)]
        # deshacer el convenio: q_ur = (q_modelo - desfase) / signo
        return [(qm - d) / s for qm, d, s in zip(q_modelo, self.convenio.desfase_rad, self.convenio.signo)]
