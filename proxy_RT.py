import os
import threading
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

URL_MVIT = "https://moovitapp.com/tripplan/san_juan-6137/lines/es-419?customerId=NPIdiV-P9Gcj-pA7yOXVPg"
LATITUD = float(os.getenv("LATITUD", "-31.5375"))
LONGITUD = float(os.getenv("LONGITUD", "-68.5364"))
TIMEOUT_DEFAULT_MS = int(os.getenv("TIMEOUT_DEFAULT_MS", "1500"))
MAX_RETRIES = int(os.getenv("MAX_RENDER_RETRIES", "2"))
LOCK_TIMEOUT_MS = int(os.getenv("ARRIVALS_LOCK_TIMEOUT_MS", "5000"))

# Requisito del usuario: ejecutar sin headless SI o SI.
PLAYWRIGHT_HEADLESS = False

ARRIVALS_LOCK = threading.Lock()


class ArrivalRequest(BaseModel):
    linea: str = Field(..., min_length=1, examples=["129"])
    parada: str = Field(..., min_length=2, examples=["Av. Ig. De La Roza y Los Jesuitas S -A"])


app = FastAPI(
    title="Proxy RT API",
    version="1.0.0",
    description="API proxy para consultar arribos desde Moovit con Playwright.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _do_lookup(page: Any, linea: str, parada: str) -> dict[str, Any]:
    page.goto(URL_MVIT, wait_until="domcontentloaded", timeout=TIMEOUT_DEFAULT_MS * 8)
    page.wait_for_timeout(TIMEOUT_DEFAULT_MS)

    buscador = page.get_by_placeholder("Buscar una línea")
    buscador.fill(linea)
    buscador.press("Enter")
    page.wait_for_timeout(TIMEOUT_DEFAULT_MS)

    page.locator(".line-item").first.click(timeout=TIMEOUT_DEFAULT_MS * 4)

    with page.expect_response(
        lambda response: "/api/lines/linearrival" in response.url and response.status == 200,
        timeout=TIMEOUT_DEFAULT_MS * 8,
    ) as inf_resp:
        page.locator(".title").filter(has_text=parada).first.click(timeout=TIMEOUT_DEFAULT_MS * 4)
        page.wait_for_timeout(TIMEOUT_DEFAULT_MS)

    datos = inf_resp.value.json()
    arrivals = datos[0].get("arrivals", []) if isinstance(datos, list) and datos else []

    if not arrivals:
        mensaje = "No hay arribos disponibles."
        elem = page.locator("div.current.ng-star-inserted span.ng-star-inserted").first
        if elem.count() > 0:
            mensaje = elem.inner_text().strip()

        return {
            "linea": linea,
            "parada": parada,
            "arrivals": [],
            "message": mensaje,
            "raw": datos,
        }

    return {
        "linea": linea,
        "parada": parada,
        "arrivals": arrivals,
        "raw": datos,
    }


def fetch_arrivals(linea: str, parada: str) -> dict[str, Any]:
    lock_ok = ARRIVALS_LOCK.acquire(timeout=LOCK_TIMEOUT_MS / 1000)
    if not lock_ok:
        raise HTTPException(status_code=503, detail="Servicio ocupado. Reintenta en unos segundos.")

    try:
        with sync_playwright() as motor:
            browser = motor.chromium.launch(
                headless=PLAYWRIGHT_HEADLESS,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--no-zygote",
                ],
            )
            context = browser.new_context(
                geolocation={"latitude": LATITUD, "longitude": LONGITUD},
                permissions=["geolocation"],
            )
            page = context.new_page()
            page.set_default_timeout(TIMEOUT_DEFAULT_MS * 8)

            try:
                for intento in range(1, MAX_RETRIES + 1):
                    try:
                        return _do_lookup(page=page, linea=linea, parada=parada)
                    except PlaywrightTimeoutError:
                        if intento == MAX_RETRIES:
                            raise
                        page.goto("about:blank")
                        page.wait_for_timeout(500)
            except PlaywrightTimeoutError as exc:
                raise HTTPException(status_code=504, detail=f"Timeout al consultar Moovit: {exc}") from exc
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Error interno al obtener arribos: {exc}") from exc
            finally:
                page.close()
                context.close()
                browser.close()
    finally:
        ARRIVALS_LOCK.release()


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/arrivals")
def arrivals(payload: ArrivalRequest) -> dict[str, Any]:
    return fetch_arrivals(linea=payload.linea, parada=payload.parada)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("proxy_RT:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))