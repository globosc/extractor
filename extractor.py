import json
import re
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, UploadFile, File
from typing import List, Dict
import logging
import datetime

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

def fetch_title_from_url(url: str) -> str:
    try:
        logger.debug(f"Iniciando fetch_title_from_url para URL: {url}")
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        title_tag = soup.find('title')
        if title_tag and title_tag.string:
            title = title_tag.string.strip()
            logger.debug(f"Título obtenido para URL {url}: {title}")
            return title
        logger.debug(f"No se encontró título para URL {url}")
        return "No Title Found"
    except requests.RequestException as e:
        logger.error(f"Error obteniendo el título de {url}: {e}")
        return "No Title Found"

def clean_title(title: str) -> str:
    logger.debug(f"Iniciando limpieza de título: {title}")
    cleaned_title = re.sub(r'\s*[-–—]\s*[^|\n\r]*', '', title)
    cleaned_title = re.sub(r'\s*\|\s*[^|\n\r]*', '', cleaned_title)
    cleaned_title = cleaned_title.strip()
    logger.debug(f"Título limpio: {cleaned_title}")
    return cleaned_title

def extract_news_headlines_from_file(file: UploadFile) -> List[Dict[str, str]]:
    try:
        logger.debug("Iniciando extract_news_headlines_from_file")
        data = json.load(file.file)
        logger.debug(f"Datos cargados desde el archivo: {data}")
    except json.JSONDecodeError as e:
        logger.error(f"Error decodificando JSON: {e}")
        raise HTTPException(status_code=400, detail="Archivo JSON inválido")

    headlines = []
    for result in data.get("results", []):
        url = result.get("url", "No URL")
        category = result.get("category", "No Category")
        source = result.get("source", "No Source")
        short_url = result.get("short_url", "No Short URL")
        date = result.get("date", "No Date")
        diminutive = result.get("diminutive", "No Diminutive")
        content_length = result.get("content_length", "No Content Length")
        sentiment = result.get("sentiment", "No Sentiment")
        keywords = result.get("keywords", "No Keywords")
        popularity = result.get("popularity", "No Popularity")
        subcategory = result.get("subcategory", "No Subcategory")
        holding = result.get("holding", "No Holding")

        target_url = short_url if short_url != "No Short URL" else url
        logger.debug(f"Obteniendo título para URL: {target_url}")
        title = fetch_title_from_url(target_url)
        cleaned_title = clean_title(title)

        headline = {
            "url": url,
            "category": category,
            "source": source,
            "short_url": short_url,
            "title": cleaned_title,
            "date": date,
            "diminutive": diminutive,
            "content_length": content_length,
            "sentiment": sentiment,
            "keywords": keywords,
            "popularity": popularity,
            "subcategory": subcategory,
            "holding": holding
        }

        logger.debug(f"Headline extraído: {headline}")
        headlines.append(headline)

    return headlines

@app.post("/headlines", response_model=List[Dict[str, str]])
async def get_headlines(file: UploadFile = File(...)):
    logger.debug(f"Solicitud POST recibida en /headlines con archivo: {file.filename}")
    if not file.filename.endswith('.json'):
        logger.error(f"Tipo de archivo inválido: {file.filename}")
        raise HTTPException(status_code=400, detail="Tipo de archivo inválido. Solo se aceptan archivos JSON.")

    headlines = extract_news_headlines_from_file(file)

    if not headlines:
        logger.error("No se encontraron titulares")
        raise HTTPException(status_code=404, detail="No se encontraron titulares")

    now = datetime.datetime.now()
    filename = f"extractor_{now.strftime('%Y%m%d_%H')}.json"

    output_path = f"/home/globoscx/unews/salidas/extractor/{filename}"
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(headlines, f, ensure_ascii=False, indent=4)
        logger.info(f"Titulares guardados en {output_path}")
    except IOError as e:
        logger.error(f"Error guardando el archivo {output_path}: {e}")
        raise HTTPException(status_code=500, detail="Error Interno del Servidor")

    return headlines

@app.get("/health")
def health_check():
    logger.debug("Solicitud GET recibida en /health")
    return {"status": "ok"}
