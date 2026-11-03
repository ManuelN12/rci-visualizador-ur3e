# Pregunta 1 · ¿Cuántos bytes devuelve cada recv()?

**Fecha:** 3 de noviembre de 2026 · URSim 5.25.2 en VirtualBox (VM 10.164.57.193), cliente en el portátil por Wi‑Fi.
Registros: `recv_primaria.csv` y `recv_tiempo_real.csv` (hora y bytes de cada llamada a `recv(65536)`).

## Interfaz primaria (30001) · 946 llamadas en 55 s

| Bytes devueltos | Veces | Qué contienen |
|---|---|---|
| 9 | 471 | Un mensaje de tipo 5 entero |
| 722 | 427 | Un mensaje de estado (tipo 16) entero |
| 743 | 43 | Un mensaje de estado con un subpaquete extra |
| 136, 181, 881, **1460**, 17 | 1 cada uno | **Las cinco primeras llamadas**, al conectar |

Al conectar, el controlador envía de golpe el mensaje de versión y otros mensajes iniciales, y esas cinco primeras
llamadas devuelven trozos que **no coinciden con ningún mensaje**: cortan mensajes por la mitad o juntan varios.
Una de ellas trae **1460 B**, el tamaño máximo de datos de un segmento TCP sobre Ethernet (MSS = 1500 de MTU − 20 de IP −
20 de TCP): el emisor partió los datos en segmentos y `recv` entregó lo que había llegado.

A partir de ahí, con un mensaje cada 100 ms y el cliente leyendo enseguida, cada `recv` trae justo un mensaje.

## Interfaz de tiempo real (30003) · 14 023 llamadas en 45,5 s (≈ 308 paquetes/s)

| Bytes devueltos | Veces | Qué contienen |
|---|---|---|
| 1220 | 14 022 | Un paquete entero |
| **3660** | 1 | **Tres paquetes juntos** (la primera llamada: se habían acumulado mientras se conectaba) |

## Respuesta

**No siempre coincide.** En régimen normal, con poco tráfico y un cliente rápido, casi todas las llamadas devuelven un
mensaje exacto, y un programa ingenuo que tratara cada `recv` como un mensaje *parecería* funcionar. Pero en cuanto el
emisor manda varios mensajes seguidos (al conectar) o el cliente se retrasa, `recv` devuelve trozos o varios mensajes
juntos: en estas mismas medidas aparecen 1460 B (medio mensaje y fragmentos) y 3660 B (tres paquetes).

**Consecuencia para el código:** no se puede suponer que un `recv` es un mensaje. Hay que acumular los bytes en un búfer y
cortar cada mensaje por la longitud de sus primeros 4 bytes (`ur_protocolo.BufferTramas`). Con el robot falso en modo
`--trocear`, que envía trozos aleatorios de 1 a 700 bytes, el búfer reconstruye correctamente todos los mensajes.
