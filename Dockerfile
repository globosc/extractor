# Imagen base con Python + Playwright + navegadores + deps del sistema
FROM mcr.microsoft.com/playwright/python

# Variables de entorno
ENV TZ=America/Santiago \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_USER=extractor \
    APP_HOME=/home/extractor

# Crear usuario y directorios
RUN useradd --create-home ${APP_USER} \
    && mkdir -p /app ${APP_HOME}/salidas /app/logs \
    && chown -R ${APP_USER}:${APP_USER} /app ${APP_HOME} /app/logs

# Establece el directorio de trabajo
WORKDIR /app

# Copiar el código
COPY --chown=${APP_USER}:${APP_USER} . /app

# Instalar las dependencias necesarias de Python (ya trae pip y playwright)
RUN pip install \
    fastapi \
    uvicorn \
    aiohttp \
    beautifulsoup4 \
    python-multipart \
    httpx \
    requests \
    playwright && playwright install --with-deps

# Cambiar a usuario no privilegiado
USER ${APP_USER}

# Exponer el puerto de la app
EXPOSE 8000

# Comando de ejecución con Uvicorn
CMD ["uvicorn", "extractor:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--timeout-keep-alive", "65"]