"""Lectura del fichero de configuración de robots (JSON).

Las IP y puertos de los robots no se escriben en el código: se cambian en el fichero.
Así el mismo programa sirve para URSim en el aula y para un UR3e real en el laboratorio.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import radians
from pathlib import Path
from typing import List, Optional

FICHERO_POR_DEFECTO = Path(__file__).parent / "config" / "robots.json"


@dataclass
class ConfigRobot:
    nombre: str
    ip: str
    puerto_primaria: int = 30001
    puerto_tiempo_real: int = 30003
    pose: List[float] = field(default_factory=lambda: [0.0] * 6)  # x, y, z (m), roll, pitch, yaw (rad)


@dataclass
class ConvenioAngulos:
    """Corrección entre los ángulos del UR y los del modelo de PyBullet.

    q_modelo[i] = signo[i] * q_ur[i] + desfase[i]
    Por defecto no corrige nada. Se ajusta en el aula si alguna articulación sale girada.
    """
    signo: List[float] = field(default_factory=lambda: [1.0] * 6)
    desfase_rad: List[float] = field(default_factory=lambda: [0.0] * 6)

    def aplicar(self, q: List[float]) -> List[float]:
        return [s * qi + d for s, qi, d in zip(self.signo, q, self.desfase_rad)]


@dataclass
class Configuracion:
    robots: List[ConfigRobot]
    convenio: ConvenioAngulos

    def robot(self, nombre: Optional[str] = None) -> ConfigRobot:
        if nombre is None:
            return self.robots[0]
        for r in self.robots:
            if r.nombre == nombre:
                return r
        disponibles = ", ".join(r.nombre for r in self.robots)
        raise ValueError(f"No hay ningún robot '{nombre}' en la configuración (hay: {disponibles})")


def cargar(ruta: Optional[str] = None) -> Configuracion:
    ruta = Path(ruta) if ruta else FICHERO_POR_DEFECTO
    with open(ruta, encoding="utf-8-sig") as f:   # -sig: admite ficheros guardados con BOM (Bloc de notas, PowerShell)
        datos = json.load(f)

    robots = []
    for r in datos.get("robots", []):
        robot = ConfigRobot(
            nombre=r["nombre"],
            ip=r["ip"],
            puerto_primaria=int(r.get("puerto_primaria", 30001)),
            puerto_tiempo_real=int(r.get("puerto_tiempo_real", 30003)),
            pose=[float(v) for v in r.get("pose", [0, 0, 0, 0, 0, 0])],
        )
        if len(robot.pose) != 6:
            raise ValueError(f"{robot.nombre}: 'pose' debe tener 6 valores [x, y, z, roll, pitch, yaw]")
        robots.append(robot)
    if not robots:
        raise ValueError(f"{ruta}: no hay ningún robot en la lista 'robots'")

    c = datos.get("convenio_angulos", {})
    convenio = ConvenioAngulos(
        signo=[float(v) for v in c.get("signo", [1] * 6)],
        desfase_rad=[radians(float(v)) for v in c.get("desfase_grados", [0] * 6)],
    )
    return Configuracion(robots, convenio)
