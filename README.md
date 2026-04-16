# 🚌 API Proxy — Red Tulum

> Proxy HTTP para obtener tiempos de arribo de colectivos en tiempo real sobre la red de transporte público de Red Tulum.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Playwright](https://img.shields.io/badge/Playwright-latest-2EAD33?style=flat-square&logo=playwright&logoColor=white)](https://playwright.dev)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![License](https://img.shields.io/badge/Licencia-MIT-yellow?style=flat-square)](LICENSE)

---

## 📋 Tabla de contenidos

- [Descripción](#-descripción)
- [¿Cómo funciona?](#-cómo-funciona)
- [Evolución del proyecto](#-evolución-del-proyecto)
- [Stack tecnológico](#-stack-tecnológico)
- [Requisitos](#-requisitos)
- [Instalación](#-instalación)
- [Uso](#-uso)
- [Endpoints](#-endpoints)
- [Scripts de indexación](#-scripts-de-indexación)
- [Estructura del proyecto](#-estructura-del-proyecto)
- [Créditos](#-créditos)
- [Aviso legal](#%EF%B8%8F-aviso-legal)

---

## 📖 Descripción

Este proxy surgió como solución a una necesidad concreta dentro del desarrollo de una PWA de control y seguimiento de transporte público local: **obtener, en tiempo real y de forma confiable, los tiempos de arribo de cada colectivo en cada parada de la red de Red Tulum**.

El núcleo de la solución consiste en aprovechar la funcionalidad pública del sitio de Red Tulum de manera eficiente, sin depender de integraciones burocráticas. Mediante una instancia web automatizada con Playwright, el proxy localiza líneas y paradas directamente en la interfaz pública e intercepta de forma selectiva las solicitudes hacia la API de Moovit, recuperando los datos de arribo en tiempo real.

El resultado es un endpoint HTTP limpio que se comporta funcionalmente de manera idéntica a la API de Moovit, consumible desde cualquier cliente.

---

## ⚙️ ¿Cómo funciona?

```
Cliente HTTP
     │
     ▼
┌─────────────────────────────────┐
│        FastAPI + Uvicorn        │
│   (recibe línea + ID parada)    │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│    Playwright (instancia web)   │
│  Abre URL canónica de la línea  │
│  Localiza parada por ID en DOM  │
│  Intercepta petición a Moovit   │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│          API de Moovit          │
│    (tiempos de arribo reales)   │
└────────────────┬────────────────┘
                 │
                 ▼
        Respuesta al cliente
     (tiempos de arribo en JSON)
```

**Flujo resumido:**
1. El cliente envía una petición con la URL canónica de la línea y el ID de la parada.
2. Playwright abre directamente la página de esa línea en Red Tulum.
3. Se localiza la parada mediante su ID en el DOM (acceso en tiempo constante).
4. Se intercepta la solicitud saliente hacia la API de Moovit.
5. Los tiempos de arribo son devueltos como respuesta JSON al cliente.

---

## 🔬 Evolución del proyecto

El diseño actual es resultado de tres iteraciones. Las dos primeras fueron descartadas por limitaciones estructurales.

### ❌ V1 — Scraping total *(descartado)*

La primera aproximación consistió en scrapear exhaustivamente el sitio: recorrer cada línea, cada parada y cada horario para consolidar todo en un archivo JSON.

**Por qué falló:**
- **Error semántico:** se asumió que los horarios eran genéricos por franja horaria, cuando en realidad corresponden al momento exacto de la consulta.
- **Error funcional:** el tiempo de ejecución del scraping completo era prohibitivo para uso en tiempo real.
- **Error de navegación:** el desplazamiento vertical del contenedor de líneas se reiniciaba al regresar del detalle, ralentizando el proceso exponencialmente. La barra de búsqueda, que habría evitado este problema, no fue considerada.

---

### ❌ V2 — Búsqueda secuencial de paradas *(descartado)*

Adopta un enfoque más conservador: usa la barra de búsqueda para localizar líneas y recorre secuencialmente las paradas hasta encontrar la solicitada. Los tiempos de arribo ya no se persisten en archivo, sino que se devuelven como respuesta directa.

**Por qué falló:**
- El procesamiento secuencial de paradas imponía complejidad lineal con impacto directo en el rendimiento.
- La coincidencia exacta del nombre de la parada como condición de búsqueda era prácticamente imposible de garantizar desde un consumidor externo.

---

### ✅ V3 — Indexación directa por URLs e IDs *(versión actual)*

Resuelve de raíz las limitaciones anteriores aprovechando dos características del sitio que no habían sido identificadas:

**1. URLs canónicas por línea**
Cada línea tiene una URL única y canónica en el sitio de Red Tulum. Esto elimina la apertura de la web principal, la interacción con el buscador y la espera de carga, **ahorrando entre 4 y 5 segundos por consulta**.

**2. Pre-indexación de paradas**
Dado que todas las paradas de una línea se cargan en el DOM al acceder a ella, se desarrollaron dos scripts complementarios para construir un índice previo:

- `collect_urls.py` — Itera la lista maestra de líneas y captura su URL canónica mediante Playwright. Persiste el resultado en `lines.json`.
- `collect_stops.py` — Captura la lista completa de paradas de cada línea, incluyendo el ID del elemento `div` en el DOM. Persiste el resultado en `stops.json`.

El proxy recibe como parámetros únicamente la URL canónica y el ID de parada, **reduciendo el acceso a tiempo constante** sin ninguna búsqueda secuencial.

---

## 🛠 Stack tecnológico

| Tecnología | Rol |
|---|---|
| **Python 3.11+** | Lenguaje base del proyecto |
| **Playwright** | Automatización web y scraping |
| **FastAPI** | Framework para exponer la API HTTP |
| **Uvicorn** | Servidor ASGI para FastAPI |
| **Docker** | Empaquetado y portabilidad del entorno |

---

## 📦 Requisitos

- Python 3.11+
- Docker y Docker Compose *(recomendado)*
- O bien: pip + Playwright instalado localmente

---

## 🚀 Instalación

### Con Docker *(recomendado)*

```bash
git clone https://github.com/[tu-usuario]/red-tulum-proxy.git
cd red-tulum-proxy
docker compose up --build
```

### Sin Docker

```bash
git clone https://github.com/[tu-usuario]/red-tulum-proxy.git
cd red-tulum-proxy

pip install -r requirements.txt
playwright install chromium

uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 📡 Uso

Una vez levantado el servicio, el proxy queda disponible en `http://localhost:8000`.

### Consulta de tiempos de arribo

```http
GET /arrivals?line_url={url_canonica}&stop_id={id_parada}
```

**Parámetros:**

| Parámetro | Tipo | Descripción |
|---|---|---|
| `line_url` | `string` | URL canónica de la línea (obtenida con `collect_urls.py`) |
| `stop_id` | `string` | ID del div de la parada en el DOM (obtenido con `collect_stops.py`) |

**Ejemplo:**

```bash
curl "http://localhost:8000/arrivals?line_url=https://redtulum.com.ar/linea/123&stop_id=stop_456"
```

**Respuesta:**

```json
{
  "line": "Línea 123",
  "stop": "Parada Av. Corrientes",
  "arrivals": [
    { "minutes": 3, "vehicle_id": "ABC-123" },
    { "minutes": 11, "vehicle_id": "DEF-456" }
  ]
}
```

---

## 📂 Scripts de indexación

Antes de usar el proxy, es necesario construir los archivos de índice. Ejecutar **una sola vez** (o al actualizar la red de líneas).

### 1. Recolectar URLs de líneas

```bash
python scripts/collect_urls.py
```

Genera `data/lines.json` con el mapa `nombre_de_línea → URL canónica`.

### 2. Recolectar paradas

```bash
python scripts/collect_stops.py
```

Genera `data/stops.json` con el mapa `línea → lista de paradas con IDs`.

> ⚠️ Estos scripts abren una instancia de Chromium automatizada. El tiempo de ejecución depende de la cantidad de líneas en la red.

---

## 🗂 Estructura del proyecto

```
red-tulum-proxy/
├── main.py                  # Entrypoint FastAPI
├── proxy/
│   └── scraper.py           # Lógica de Playwright e intercepción
├── scripts/
│   ├── collect_urls.py      # Script de indexación de URLs
│   └── collect_stops.py     # Script de indexación de paradas
├── data/
│   ├── lines.json           # Índice de líneas (generado)
│   └── stops.json           # Índice de paradas (generado)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 🙏 Créditos

| Rol | Proyecto |
|---|---|
| **Fuente de datos** | [Red Tulum](https://redtulum.com.ar) |
| **API de tiempos reales** | [Moovit](https://moovitapp.com) |
| **Automatización web** | [Playwright](https://playwright.dev) |
| **Framework API** | [FastAPI](https://fastapi.tiangolo.com) |
| **Servidor ASGI** | [Uvicorn](https://uvicorn.org) |
| **Contenedores** | [Docker](https://docker.com) |

---

## ⚖️ Aviso legal

Este software accede exclusivamente a información de carácter **público**, disponible de forma libre y sin restricción de acceso en el sitio web oficial de Red Tulum. En ningún caso se accede, procesa ni almacena información privada, sensible o protegida bajo credenciales de autenticación.

Las peticiones realizadas replican el comportamiento de un usuario final navegando la interfaz pública. No se infringen mecanismos de protección técnica ni se vulneran términos de uso que prohíban expresamente el acceso automatizado a datos públicos.

Este proyecto **no posee afiliación oficial** con Red Tulum ni con Moovit. El uso de sus datos se realiza con fines de interés público e integración de servicios, reconociendo la autoría y titularidad de dichas plataformas sobre su información.

El desarrollador no asume responsabilidad por el uso derivado de este proxy ni por cambios en la disponibilidad o estructura de las fuentes de datos externas.

---

<p align="center">
  Desarrollado con ☕ por <a href="https://github.com/[tu-usuario]">DJ Solutions</a>
</p>
