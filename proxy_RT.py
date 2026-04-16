import os
import threading
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

LATITUD = float(os.getenv("LATITUD", "-31.5375"))
LONGITUD = float(os.getenv("LONGITUD", "-68.5364"))
TIMEOUT_DEFAULT_MS = int(os.getenv("TIMEOUT_DEFAULT_MS", "1500"))
MAX_RETRIES = int(os.getenv("MAX_RENDER_RETRIES", "2"))
LOCK_TIMEOUT_MS = int(os.getenv("ARRIVALS_LOCK_TIMEOUT_MS", "5000"))

# Requisito del usuario: ejecutar sin headless SI o SI.
PLAYWRIGHT_HEADLESS = False

ARRIVALS_LOCK = threading.Lock()


class ArrivalRequest(BaseModel):
    url: str = Field(..., min_length=8, examples=["https://example.com/"])
    id_p: str = Field(..., min_length=1, examples=["stop-123"])


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


def _do_lookup(page: Any, url: str, id_p: str) -> dict[str, Any]:
    page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_DEFAULT_MS * 8)
    page.wait_for_timeout(2000)

    selector_objetivo = f'[id="{id_p}"]'
    try:
        page.wait_for_selector(selector_objetivo, state="attached", timeout=TIMEOUT_DEFAULT_MS * 8)
    except PlaywrightTimeoutError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró un elemento con id '{id_p}' en el DOM (timeout esperando selector).",
        ) from exc

    objetivo = page.locator(selector_objetivo).first

    with page.expect_response(
        lambda response: "/api/lines/linearrival" in response.url and response.status == 200,
        timeout=TIMEOUT_DEFAULT_MS * 8,
    ) as inf_resp:
        objetivo.click(timeout=TIMEOUT_DEFAULT_MS * 4)

    datos = inf_resp.value.json()
    page.wait_for_timeout(500)
    arrivals: list[Any] = []
    if isinstance(datos, list) and datos:
        arrivals = datos[0].get("arrivals", []) if isinstance(datos[0], dict) else []

    if not arrivals:
        horario_estimado: str | None = None
        elem = page.locator("div.current.ng-star-inserted span.ng-star-inserted").first
        if elem.count() > 0:
            horario_estimado = elem.inner_text().strip()

        return {
            "id_p": id_p,
            "arrivals": [],
            "horario_estimado": horario_estimado,
            "raw": datos,
        }

    return {
        "id_p": id_p,
        "arrivals": arrivals,
        "raw": datos,
    }


def fetch_arrivals(url: str, id_p: str) -> dict[str, Any]:
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
                        return _do_lookup(page=page, url=url, id_p=id_p)
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
    return fetch_arrivals(url=payload.url, id_p=payload.id_p)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("proxy_RT:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))