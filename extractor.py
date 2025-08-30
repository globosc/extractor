import json
import re
import aiohttp
import asyncio
from fastapi import FastAPI, HTTPException, UploadFile, File
from typing import List, Dict
import logging
import datetime
from pathlib import Path
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# Configuraciones
MAX_CONCURRENT_REQUESTS = 5
BATCH_SIZE = 10
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
OUTPUT_DIR = Path("/home/extractor/salidas")

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Crear directorio de salidas si no existe
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()


async def extract_exante_title(url: str) -> str:
    """Extrae el título de EX-ANTE usando Playwright async, con fallback, espera y debug."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=30000)
            
            # Esperar el selector h1 (hasta 5 segundos)
            try:
                await page.wait_for_selector("h1", timeout=5000)
            except Exception:
                logger.warning("No apareció <h1> dentro del timeout")

            # Intentar varios selectores por orden de prioridad
            selectors = [
                "h1",
                ".entry-title",
                "[role=heading]",
                "meta[property='og:title']",
                "title"
            ]

            for selector in selectors:
                try:
                    if selector.startswith("meta"):
                        element = await page.locator(selector).first.get_attribute("content")
                    elif selector == "title":
                        element = await page.title()
                    else:
                        element = await page.locator(selector).first.text_content()
                    
                    if element:
                        title = element.strip()
                        await browser.close()
                        logger.info(f"Título extraído de EX-ANTE con selector '{selector}': {title}")
                        return title
                except Exception as e:
                    logger.warning(f"No se pudo extraer con selector {selector}: {e}")

            # Dump del HTML y screenshot para depurar
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            html_path = OUTPUT_DIR / f"debug_exante_{timestamp}.html"
            img_path = OUTPUT_DIR / f"debug_exante_{timestamp}.png"

            try:
                html = await page.content()
                await page.screenshot(path=str(img_path))
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html)
                logger.warning(f"Dump generado: {html_path} y {img_path}")
            except Exception as e:
                logger.error(f"No se pudo guardar el dump de EX-ANTE: {e}")
            finally:
                await browser.close()

            return "No Title Found"

    except Exception as e:
        logger.error(f"Error con Playwright async para EX-ANTE: {str(e)}")
        return "No Title Found"


async def fetch_title_from_url(url: str, session: aiohttp.ClientSession) -> str:
    """Obtiene el título de una URL con reintentos y estrategias específicas por dominio."""
    parsed_url = urlparse(url)
    domain = parsed_url.netloc

    if "ex-ante.cl" in domain:
        logger.info(f"Usando extractor especial para EX-ANTE: {url}")
        return await extract_exante_title(url)

    for attempt in range(MAX_RETRIES):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3",
                "Referer": "https://www.google.com/"
            }
            
            async with session.get(url, timeout=REQUEST_TIMEOUT, headers=headers) as response:
                if response.status == 200:
                    content = await response.text()
                    soup = BeautifulSoup(content, 'html.parser')

                    # Intentar extraer título en orden de prioridad
                    og_title = soup.find('meta', property='og:title')
                    if og_title and og_title.get('content'):
                        return og_title.get('content').strip()

                    twitter_title = soup.find('meta', attrs={'name': 'twitter:title'})
                    if twitter_title and twitter_title.get('content'):
                        return twitter_title.get('content').strip()

                    h1_tag = soup.find('h1')
                    if h1_tag and h1_tag.text.strip():
                        return h1_tag.text.strip()

                    title_tag = soup.find('title')
                    if title_tag and title_tag.string:
                        return title_tag.string.strip()

                    return "No Title Found"

                logger.warning(f"Intento {attempt + 1}: Status {response.status} para URL {url}")

        except asyncio.TimeoutError:
            logger.warning(f"Timeout en intento {attempt + 1} para URL {url}")
        except Exception as e:
            logger.error(f"Error en intento {attempt + 1} para URL {url}: {str(e)}")

        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(2 ** attempt)

    return "No Title Found"


def clean_title(title: str) -> str:
    """Limpia el título removiendo sufijos de sitios web."""
    if not isinstance(title, str):
        return "No Title Found"
    
    # Remover sufijos comunes de sitios
    cleaned_title = re.sub(r'\s*[\|\-\u2013\u2014]\s*Ex[-\s]?Ante.*$', '', title)
    cleaned_title = re.sub(r'\s*[\|\-\u2013\u2014]\s*El Líbero.*$', '', cleaned_title)
    
    return cleaned_title.strip()


async def process_urls_batch(urls_data: List[Dict], session: aiohttp.ClientSession) -> List[Dict]:
    """Procesa un lote de URLs de forma concurrente con control de semáforo."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async def process_single_url(data: Dict) -> Dict:
        async with semaphore:
            target_url = data.get("url")
            if not target_url:
                logger.error(f"URL no encontrada en los datos: {data}")
                data["title"] = "No Title Found"
                return data

            logger.info(f"Extrayendo título de URL original: {target_url}")
            title = await fetch_title_from_url(target_url, session)
            data["title"] = clean_title(title)
            logger.info(f"Título extraído: '{data['title']}' de URL: {target_url}")
            return data

    return await asyncio.gather(*[process_single_url(data) for data in urls_data])


async def extract_news_headlines_from_file(file: UploadFile) -> List[Dict[str, str]]:
    """Procesa un archivo JSON con URLs y extrae los títulos de cada una."""
    try:
        logger.info(f"Iniciando procesamiento del archivo: {file.filename}")
        content = await file.read()
        data = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(f"Error decodificando JSON: {e}")
        raise HTTPException(status_code=400, detail="Archivo JSON inválido")

    # Manejar diferentes formatos de JSON
    if isinstance(data, list):
        results = data
    elif isinstance(data, dict):
        results = data.get("results") or next((v for v in data.values() if isinstance(v, list)), None)
        if results is None:
            raise HTTPException(status_code=400, detail="No se encontró una lista de URLs en el JSON")
    else:
        raise HTTPException(status_code=400, detail="Formato JSON no reconocido")

    logger.info(f"Archivo {file.filename} contiene {len(results)} URLs para procesar")

    # Configurar cliente HTTP con límites
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS, ssl=False)
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        headlines = []
        total_batches = (len(results) + BATCH_SIZE - 1) // BATCH_SIZE
        
        for i in range(0, len(results), BATCH_SIZE):
            batch = results[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            
            logger.info(f"Procesando lote {batch_num} de {total_batches} del archivo {file.filename}")
            processed_batch = await process_urls_batch(batch, session)
            headlines.extend(processed_batch)
            
            # Pausa entre lotes para evitar sobrecarga
            await asyncio.sleep(0.5)

    logger.info(f"Completado procesamiento de {len(headlines)} URLs del archivo {file.filename}")
    return headlines


@app.post("/headlines", response_model=List[Dict[str, str]])
async def get_headlines(file: UploadFile = File(...)):
    """Endpoint principal para procesar archivo JSON y extraer títulos de noticias."""
    logger.info(f"Procesando archivo: {file.filename}")

    if not file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos JSON")

    headlines = await extract_news_headlines_from_file(file)
    if not headlines:
        raise HTTPException(status_code=404, detail="No se encontraron titulares")

    # Generar nombre de archivo con timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H")
    output_path = OUTPUT_DIR / f"extractor_{timestamp}.json"

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(headlines, f, ensure_ascii=False, indent=4)
        logger.info(f"Resultados guardados en {output_path}")
    except Exception as e:
        logger.error(f"Error guardando resultados: {e}")
        raise HTTPException(status_code=500, detail=f"Error guardando resultados: {str(e)}")

    return headlines


@app.get("/health")
async def health_check():
    """Endpoint de salud para verificar que el servicio está funcionando."""
    return {
        "status": "ok", 
        "timestamp": datetime.datetime.now().isoformat(),
        "output_dir": str(OUTPUT_DIR)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)