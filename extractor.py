import json
import re
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, UploadFile, File
from typing import List, Dict
import logging
import datetime
from pathlib import Path

# Configuraciones
MAX_CONCURRENT_REQUESTS = 5
BATCH_SIZE = 10
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
OUTPUT_DIR = Path("/home/globoscx/unews/salidas/extractor")

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

async def fetch_title_from_url(url: str, session: aiohttp.ClientSession) -> str:
    """Obtiene el título de una URL con reintentos."""
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(url, timeout=REQUEST_TIMEOUT) as response:
                if response.status == 200:
                    content = await response.text()
                    soup = BeautifulSoup(content, 'html.parser')
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
            await asyncio.sleep(2 ** attempt)  # Espera exponencial
    
    return "No Title Found"

def clean_title(title: str) -> str:
    """Limpia el título removiendo partes innecesarias."""
    cleaned_title = re.sub(r'\s*[-–—]\s*[^|\n\r]*', '', title)
    cleaned_title = re.sub(r'\s*\|\s*[^|\n\r]*', '', cleaned_title)
    return cleaned_title.strip()

async def process_urls_batch(urls_data: List[Dict], session: aiohttp.ClientSession) -> List[Dict]:
    """Procesa un lote de URLs en paralelo."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
    async def process_single_url(data: Dict) -> Dict:
        async with semaphore:
            target_url = data.get("short_url", data.get("url", "No URL"))
            if target_url == "No URL":
                logger.error(f"URL no encontrada en los datos: {data}")
                return data
            
            title = await fetch_title_from_url(target_url, session)
            data["title"] = clean_title(title)
            return data
    
    return await asyncio.gather(*[process_single_url(data) for data in urls_data])

async def extract_news_headlines_from_file(file: UploadFile) -> List[Dict[str, str]]:
    """Extrae títulos de noticias del archivo JSON."""
    try:
        content = await file.read()
        data = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(f"Error decodificando JSON: {e}")
        raise HTTPException(status_code=400, detail="Archivo JSON inválido")

    if not isinstance(data, dict) or "results" not in data:
        raise HTTPException(status_code=400, detail="Formato JSON inválido: se espera un objeto con campo 'results'")

    results = data["results"]
    if not isinstance(results, list):
        raise HTTPException(status_code=400, detail="El campo 'results' debe ser una lista")

    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS, ssl=False)
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        headlines = []
        for i in range(0, len(results), BATCH_SIZE):
            batch = results[i:i + BATCH_SIZE]
            processed_batch = await process_urls_batch(batch, session)
            headlines.extend(processed_batch)
            await asyncio.sleep(0.5)  # Pequeña pausa entre lotes

    return headlines

@app.post("/headlines", response_model=List[Dict[str, str]])
async def get_headlines(file: UploadFile = File(...)):
    """Endpoint principal para procesar archivos JSON con URLs."""
    logger.info(f"Procesando archivo: {file.filename}")
    
    if not file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos JSON")

    headlines = await extract_news_headlines_from_file(file)
    
    if not headlines:
        raise HTTPException(status_code=404, detail="No se encontraron titulares")

    # Guardar resultados
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H")
    output_path = OUTPUT_DIR / f"extractor_{timestamp}.json"
    
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(headlines, f, ensure_ascii=False, indent=4)
        logger.info(f"Resultados guardados en {output_path}")
    except Exception as e:
        logger.error(f"Error guardando resultados: {e}")
        raise HTTPException(status_code=500, detail=f"Error guardando resultados: {str(e)}")

    return headlines

@app.get("/health")
async def health_check():
    """Endpoint de verificación de salud."""
    return {"status": "ok", "timestamp": datetime.datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)