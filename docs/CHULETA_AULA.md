# Chuleta para el aula · lunes

Objetivo de hoy: **validar el nivel aprobado con URSim** y apuntar las medidas para la memoria.
Tiempo estimado: 1,5–2 h.

> Consejo: en PowerShell, añade `| Tee-Object medidas\aula_XX.txt` al final de una orden para verla **y** guardarla
> a la vez. Al terminar cada paso, puedes pegarme la salida en el chat y la revisamos.

---

## 0 · Antes de salir de casa

- [ ] Publicar el repo `rci-visualizador-ur3e` con GitHub Desktop (*File → Add local repository* → *Publish*).
- [ ] Llevar el fichero `ur3e_rg2-0.1.0-py3-none-any.whl` (aula virtual, o en un USB).

## 1 · Bajar el código al PC del aula

- Con GitHub Desktop o git: clonar el repo.
- Sin nada instalado: en github.com, tu repo → **Code → Download ZIP** y descomprimir.

## 2 · Hito A0 · Máquina virtual y red

1. VirtualBox, **con la VM apagada**: *Configuración → Red → Adaptador 1 → Adaptador puente*, y en *Nombre* la tarjeta
   **Ethernet cableada** (no Wi‑Fi ni virtual).
2. Arrancar la VM y, en un terminal de la VM: `ip addr`. Apuntar su IP (debe ser `10.172.18.x`).
   - IP de mi VM: `10.172.18.178`
3. Desde el PC (PowerShell):
   ```powershell
   ping 10.172.18.____
   Test-NetConnection 10.172.18.____ -Port 30001
   Test-NetConnection 10.172.18.____ -Port 30003
   ```
   Debe salir `TcpTestSucceeded : True` en los dos puertos. Si sale `False`, el robot no está arrancado (paso 4)
   o hay un problema de red: **diagnóstico por capas** (enlace → ping → puerto).
4. En URSim (PolyScope): botón de inicio → **ON** → **START** → estado **Normal**.
5. Apuntar la versión de PolyScope (la mostrará también `primaria.py` al conectar).

## 3 · Python y visualizador

```powershell
cd ruta\a\rci-visualizador-ur3e
python --version
python -c "import pybullet, UR3e_rg2; print('visualizador OK')"
```

- Si dice **visualizador OK**: no hace falta instalar nada, usa ese Python.
- Si no:
  ```powershell
  python -m venv venv
  venv\Scripts\activate
  pip install ruta\a\ur3e_rg2-0.1.0-py3-none-any.whl
  ```
  - Si `activate` da error de permisos en PowerShell, usa directamente `venv\Scripts\python.exe` en lugar de `python`.
  - Si `pip` falla compilando `pybullet`: **pregunta al profesor** cómo está instalado en las prácticas.
    Mientras tanto, todos los hitos salvo A5 y B4 funcionan sin PyBullet.

## 4 · Configurar la IP

Editar `config\robots.json` y poner la IP de tu VM en `"ip"`. **No se toca el código.**

## 5 · Bloque A · interfaz primaria

| Hito | Orden | Qué mirar | Anotar |
|---|---|---|---|
| A1 | `python primaria.py --modo bytes --registro medidas\recv_primaria.csv` (dejar **1 minuto**) | Los bytes de cada `recv()` varían | ¿Algún recv con 2 mensajes? ¿Con medio? |
| A2 | `python primaria.py --modo mensajes` | 1º tipo 20 (versión), luego tipo 16 unas 10 veces/s | Longitud del mensaje 16: `____` B. Versión: `________` |
| A3 | `python primaria.py --modo subpaquetes` | Todas las líneas con ✓ | Lista de subpaquetes (tipo:tamaño) |
| A4 | `python primaria.py --modo angulos` | Comparar con la pestaña **Mover** de PolyScope | ¿Coinciden los 6? |
| A5 | `python primaria.py` | Mover el robot en URSim: el de PyBullet le sigue | Captura de pantalla de los dos |

**Convenio de ángulos** (importante): en URSim, lleva el robot a **todo 0° salvo hombro y muñeca 1 a −90°**.
El de PyBullet debe quedar exactamente igual. Si alguna articulación sale girada o al revés, se corrige en
`config\robots.json` → `convenio_angulos` (`signo` o `desfase_grados`), **nunca en el módulo del profesor**.
Haz una captura de las dos ventanas para la memoria.

## 6 · Bloque B · interfaz de tiempo real

| Hito | Orden | Qué mirar | Anotar |
|---|---|---|---|
| B1 | `python tiempo_real.py --modo paquetes` | Todos los paquetes de la misma longitud | Longitud: `____` B (1140 en 5.9, 1220 en 5.10 o posterior) |
| B2 | `python tiempo_real.py --modo frecuencia` | Unos 500 paquetes/s | Paquetes/s: `____`. Retraso: `____` ms |
| B3 | `python tiempo_real.py --modo angulos` | Igual que en A4 | ¿Coinciden? |
| B4 | `python tiempo_real.py` | Mover rápido el robot en URSim: el simulado no se queda atrás | Retraso en la línea de estado |

Opcional (pregunta 1 y 4): `python tiempo_real.py --modo bytes --registro medidas\recv_tiempo_real.csv` durante 1 minuto.

## 7 · Pruebas de robustez (las mira el profesor en la defensa)

- [ ] Con `primaria.py` en marcha, **reiniciar URSim**: el programa debe avisar, reintentar y reconectar solo, sin colgarse.
- [ ] Lo mismo con `tiempo_real.py`.
- [ ] **Pregunta 6:** cortar la red 5 s. Mejor que tirar del cable: en VirtualBox, *Dispositivos → Red → desmarcar
      «Conectar cable»* y volver a marcarlo. Anotar qué hace el programa.
- [ ] **Pregunta 7 (notable):** mover rápido en URSim y comparar a ojo el retraso del robot simulado con `primaria.py`
      y con `tiempo_real.py`.

## 8 · Preparar lo que viene

- [ ] **Reservar con el profesor el UR3e real** para la validación (idealmente jueves). Preguntar qué versión de PolyScope tienen.
- [ ] **Notable (martes):** buscar un compañero que te deje conectar a su URSim (necesitas su IP).
- [ ] **Sobresaliente:** en URSim, mirar *Ajustes → Sistema → Control remoto* y *Ajustes → Seguridad → Servicios*. Anotar
      qué opciones hay; no hace falta tocar nada todavía.

## 9 · Al terminar

- [ ] Subir lo que hayas guardado en `medidas\` (si el PC del aula no tiene GitHub: en github.com,
      *Add file → Upload files* dentro de la carpeta `medidas`, o llévatelo en un USB).
- [ ] Pegarme en el chat las salidas y anotaciones: con eso preparo el notable y voy escribiendo la memoria.
