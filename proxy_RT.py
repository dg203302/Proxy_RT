import os
import re
import threading
from typing import Any
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

URL_MOOVIT = "https://moovitapp.com/tripplan/san_juan-6137/lines/es-419?customerId=NPIdiV-P9Gcj-pA7yOXVPg"
LATITUD = float(os.getenv("LATITUD", "-31.5375"))
LONGITUD = float(os.getenv("LONGITUD", "-68.5364"))
TIMEOUT_DEFAULT_MS = int(os.getenv("TIMEOUT_DEFAULT_MS", "4000"))
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
MAX_RENDER_RETRIES = int(os.getenv("MAX_RENDER_RETRIES", "2"))
ARRIVALS_LOCK_TIMEOUT_MS = int(os.getenv("ARRIVALS_LOCK_TIMEOUT_MS", "5000"))
ARRIVALS_LOCK = threading.Lock()


class ArrivalRequest(BaseModel):
    linea: str = Field(..., min_length=1, examples=["129"])
    parada: str = Field(..., min_length=2, examples=["Av. Ig. De La Roza y Los Jesuitas S -A"])


app = FastAPI(
    title="Proxy RT API",
    version="1.0.0",
    description="API para consultar arribos de lineas por parada usando Playwright.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # El "*" permite que cualquier página se conecte. 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resolve_search_box(page: Any, timeout_ms: int) -> Any:
    candidate_selectors = [
        "input[placeholder*='linea' i]",
        "input[placeholder*='linea']",
        "input[placeholder*='line' i]",
        "input[type='search']",
        "input[aria-label*='linea' i]",
        "input[aria-label*='line' i]",
    ]

    for selector in candidate_selectors:
        locator = page.locator(selector).first
        if locator.count() > 0:
            locator.wait_for(state="visible", timeout=timeout_ms)
            return locator

    try:
        regex_locator = page.get_by_placeholder(re.compile(r"buscar una l[ií]nea", re.IGNORECASE)).first
        regex_locator.wait_for(state="visible", timeout=timeout_ms)
        return regex_locator
    except PlaywrightTimeoutError:
        pass

    raise PlaywrightTimeoutError("No se encontro el buscador de lineas en el DOM.")


def _perform_arrival_lookup(page: Any, linea: str, parada: str) -> dict[str, Any]:
    page.goto(URL_MOOVIT, wait_until="domcontentloaded", timeout=TIMEOUT_DEFAULT_MS * 6)
    page.wait_for_load_state("networkidle", timeout=TIMEOUT_DEFAULT_MS * 6)

    for text in ["Aceptar", "Acepto", "Entendido", "Aceptar todo"]:
        button = page.get_by_role("button", name=re.compile(text, re.IGNORECASE)).first
        if button.count() > 0:
            button.click(timeout=1500)
            break

    search_box = _resolve_search_box(page, timeout_ms=TIMEOUT_DEFAULT_MS * 6)
    search_box.click()
    search_box.fill(linea)
    search_box.press("Enter")

    line_item = page.locator(".line-item").first
    line_item.wait_for(state="visible", timeout=TIMEOUT_DEFAULT_MS * 6)
    line_item.click(timeout=TIMEOUT_DEFAULT_MS * 4)

    stop_item = page.locator(".title").filter(has_text=parada).first
    stop_item.wait_for(state="visible", timeout=TIMEOUT_DEFAULT_MS * 6)

    with page.expect_response(
        lambda response: "/api/lines/linearrival" in response.url and response.status == 200,
        timeout=TIMEOUT_DEFAULT_MS * 6,
    ) as arrival_response:
        stop_item.click(timeout=TIMEOUT_DEFAULT_MS * 4)

    data = arrival_response.value.json()

    if not data:
        return {
            "linea": linea,
            "parada": parada,
            "arrivals": [],
            "message": "No se recibieron datos de arribos para la parada indicada.",
        }

    arrivals = data[0].get("arrivals", []) if isinstance(data, list) else []
    if not arrivals:
        current_text = "No hay arribos disponibles."
        current_locator = page.locator("div.current.ng-star-inserted span.ng-star-inserted").first
        if current_locator.count() > 0:
            current_text = current_locator.inner_text().strip()

        return {
            "linea": linea,
            "parada": parada,
            "arrivals": [],
            "message": current_text,
        }

    return {
        "linea": linea,
        "parada": parada,
        "arrivals": arrivals,
        "raw": data,
    }

def fetch_arrivals(linea: str, parada: str) -> dict[str, Any]:
    lock_acquired = ARRIVALS_LOCK.acquire(timeout=ARRIVALS_LOCK_TIMEOUT_MS / 1000)
    if not lock_acquired:
        raise HTTPException(
            status_code=503,
            detail="Servicio ocupado. Reintenta en unos segundos.",
        )

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=PLAYWRIGHT_HEADLESS,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--no-zygote",
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            USER_AGENT_FALSO = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            context = browser.new_context(
                geolocation={"latitude": LATITUD, "longitude": LONGITUD},
                permissions=["geolocation"],
                locale="es-AR",
                viewport={"width": 1366, "height": 900},
                user_agent=USER_AGENT_FALSO  # ¡Moovit se come el amague!
            )
            context.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                """
            )
            page = context.new_page()
            page.set_default_timeout(TIMEOUT_DEFAULT_MS * 6)

            try:
                for attempt in range(1, MAX_RENDER_RETRIES + 1):
                    try:
                        return _perform_arrival_lookup(page=page, linea=linea, parada=parada)
                    except PlaywrightTimeoutError:
                        if attempt == MAX_RENDER_RETRIES:
                            raise
                        page.goto("about:blank")
                        page.wait_for_timeout(600)

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