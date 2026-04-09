from playwright.sync_api import sync_playwright
URL_mvit='https://moovitapp.com/tripplan/san_juan-6137/lines/es-419?customerId=NPIdiV-P9Gcj-pA7yOXVPg'
latitud = -31.5375
longitud = -68.5364
clase_parada_colect='.stop-item'
clase_parada_colect='.stop-item'
timeout_default=1000



linea_p = input("linea")
parada_p = input("parada")
with sync_playwright() as motor:
    naveg = motor.chromium.launch(headless=False)
    contexto = naveg.new_context(
            geolocation={"latitude": latitud, "longitude": longitud},
            permissions=["geolocation"],
        )
    pag=contexto.new_page()
    pag.goto(URL_mvit)
    pag.wait_for_timeout(timeout_default)
    buscador = pag.get_by_placeholder('Buscar una línea')
    buscador.fill(linea_p)
    buscador.press('Enter')
    pag.wait_for_timeout(timeout_default)
    results = pag.locator('.line-item').first.click()

    with pag.expect_response(
        lambda response: "/api/lines/linearrival" in response.url and response.status == 200
    ) as inf_resp:
        pag.locator('.title').filter(has_text=parada_p).click()
        pag.wait_for_timeout(timeout_default)
    try:
        datos = inf_resp.value.json()
        if not datos[0].get("arrivals"):
            elem = pag.locator("div.current.ng-star-inserted span.ng-star-inserted").first
            print(elem.inner_text().strip())
        else:
            print(datos)
    except Exception as e:
        print(f"Error al intentar extraer el JSON: {e}")

    pag.close()


#datos de prueba
#linea_p='129'
#parada_p='Av. Ig. De La Roza y Los Jesuitas S -A'