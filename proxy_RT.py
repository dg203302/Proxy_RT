import os
from typing import Any
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

URL_MOOVIT = "https://moovitapp.com/tripplan/san_juan-6137/lines/es-419?customerId=NPIdiV-P9Gcj-pA7yOXVPg"
LATITUD = float(os.getenv("LATITUD", "-31.5375"))
LONGITUD = float(os.getenv("LONGITUD", "-68.5364"))
TIMEOUT_DEFAULT_MS = int(os.getenv("TIMEOUT_DEFAULT_MS", "2500"))
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"


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

def fetch_arrivals(linea: str, parada: str) -> dict[str, Any]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
        context = browser.new_context(
            geolocation={"latitude": LATITUD, "longitude": LONGITUD},
            permissions=["geolocation"],
        )
        page = context.new_page()

        try:
            page.goto(URL_MOOVIT, wait_until="domcontentloaded", timeout=TIMEOUT_DEFAULT_MS * 4)
            page.wait_for_timeout(TIMEOUT_DEFAULT_MS)

            search_box = page.get_by_placeholder("Buscar una linea")
            search_box.fill(linea)
            search_box.press("Enter")
            page.wait_for_timeout(TIMEOUT_DEFAULT_MS)

            page.locator(".line-item").first.click(timeout=TIMEOUT_DEFAULT_MS * 2)

            with page.expect_response(
                lambda response: "/api/lines/linearrival" in response.url and response.status == 200,
                timeout=TIMEOUT_DEFAULT_MS * 4,
            ) as arrival_response:
                page.locator(".title").filter(has_text=parada).first.click(timeout=TIMEOUT_DEFAULT_MS * 2)

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


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/arrivals")
def arrivals(payload: ArrivalRequest) -> dict[str, Any]:
    return fetch_arrivals(linea=payload.linea, parada=payload.parada)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("proxy_RT:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))