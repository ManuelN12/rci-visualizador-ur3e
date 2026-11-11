# Chuleta para el laboratorio de robótica · UR3e real

Objetivo: comprobar que **el mismo programa** que funciona con URSim funciona con un UR3e real **cambiando solo la IP**,
y anotar las diferencias para la memoria.

> **Seguridad (enunciado):** los robots reales solo se usan desde los PCs del laboratorio y con el profesor presente.
> **Ninguna orden de movimiento sin su autorización expresa.** Primero solo se lee.

---

## 0 · Antes de ir

- [ ] Todo subido a GitHub (último commit y push hechos).
- [ ] **Construir el ejecutable** en mi portátil: doble clic en `construir_exe.bat` → `dist\visualizador_ur3e.zip`.
- [ ] Probarlo en mi portátil **desde la carpeta `dist`**, no desde el proyecto (ver apartado 1).
- [ ] Copiar `visualizador_ur3e.zip` a un USB.
- [ ] Preguntar al profesor qué robot me asigna.

## 1 · En el PC del laboratorio (no se instala nada)

1. Copiar el zip del USB al escritorio y **descomprimirlo** (clic derecho → *Extraer todo*). No ejecutarlo desde
   dentro del zip.
2. Abrir la carpeta `visualizador_ur3e`: dentro están `visualizador_ur3e.exe`, `config\` y `secuencias\`.
3. Editar `config\ur3e_real.json` con el Bloc de notas y poner la IP del robot asignado.
4. Doble clic en `visualizador_ur3e.exe` → menú → elegir programa, escribir `ur3e_real.json` como fichero de
   configuración y, si hace falta, las opciones (por ejemplo `--modo angulos`).

Desde una consola (`cmd` en esa carpeta) también se pueden pasar las opciones directamente. En las tablas de abajo,
`python primaria.py` equivale a `visualizador_ur3e primaria`, `python tiempo_real.py` a `visualizador_ur3e tiempo_real`,
`python varios_robots.py` a `visualizador_ur3e varios` y `python ensenar_reproducir.py` a `visualizador_ur3e ensenar`:

```
visualizador_ur3e primaria --config config\ur3e_real.json --modo angulos
```

Si Windows muestra *Windows protegió su PC* (SmartScreen) al ser un ejecutable sin firmar: *Más información →
Ejecutar de todas formas*.

## 2 · Red (diagnóstico por capas)

El PC del laboratorio está en `10.172.21.x`, como los robots: no hace falta VM.

```powershell
ipconfig                                         # mi IP: 10.172.21.____
ping 10.172.21.___                               # robot asignado
Test-NetConnection 10.172.21.___ -Port 30001
Test-NetConnection 10.172.21.___ -Port 30003
```

Poner la IP del robot en `config/ur3e_real.json` (**no se toca el código**).

## 3 · Solo lectura (el profesor mueve el robot desde su consola)

| Orden | Qué anotar |
|---|---|
| `python primaria.py --config config/ur3e_real.json --modo mensajes` | Versión de PolyScope (primer tipo 20) y longitud del mensaje de estado |
| `python primaria.py --config config/ur3e_real.json --modo subpaquetes` | Subpaquetes: ¿los mismos que URSim? ¿suman ✓? |
| `python primaria.py --config config/ur3e_real.json --modo angulos` | Ángulos frente a la consola del robot |
| `python primaria.py --config config/ur3e_real.json` | El robot de PyBullet sigue al real |
| `python tiempo_real.py --config config/ur3e_real.json --modo frecuencia` | **Paquetes/s** (URSim daba ≈ 300; el real debería dar ≈ 500) y reloj del robot (≈ 1,00 s por s real) |
| `python tiempo_real.py --config config/ur3e_real.json` | Sin retraso acumulado; ahora la columna *retraso* sí debería mostrar un valor |

## 4 · Notable (si hay dos robots libres)

Poner las IP de los dos robots en `config/dos_reales.json` y:

```
python varios_robots.py --config config/dos_reales.json
```

## 5 · Sobresaliente · SOLO con el profesor delante y su permiso

En la consola del robot: robot en *Normal*, **Remote** arriba a la derecha y, si el profesor lo pide, la velocidad
global baja (deslizador de abajo, por ejemplo 30 %).

```
python ensenar_reproducir.py --config config/ur3e_real.json
```

1. Enseñar 3–4 puntos **cercanos y despejados** (en Local con la consola o con *freedrive*, y volver a Remote).
2. `lista` y **`ver`**: revisar la trayectoria con el robot fantasma antes de mover nada.
3. Con el profesor junto a la seta de emergencia: `ejecutar`.
4. Si el profesor lo autoriza: probar `pausa` / `seguir`.

El programa ya limita `v = 0,3 rad/s` y `a = 0,5 rad/s²`, comprueba que los ángulos están en radianes (±2π) y no envía
nada si el robot no está en `RUNNING`, sin paradas y sin programa en marcha.

## 6 · Para la memoria (apuntar en el momento)

- Robot usado (IP y posición en el laboratorio) y versión de PolyScope.
- Paquetes/s en tiempo real y si `recv llenos` sigue en 0.
- Error final de cada punto (en URSim era 0,000°; en el real habrá un error pequeño de seguimiento).
- Duración real de los movimientos frente a la teórica (en URSim tardaban ≈ 1,7 veces más).
- Cualquier mensaje o comportamiento distinto de URSim.
