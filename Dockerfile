# Usa una imagen base oficial de Python
FROM python:3.9-slim

# Establece la zona horaria a Chile
ENV TZ=America/Santiago

# Argumentos para UID y GID del usuario
ARG UID
ARG GID

# Actualiza el índice de paquetes e instala dependencias necesarias
RUN apt-get update && apt-get install -y \
    curl \
    net-tools \
    iputils-ping \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Instala las dependencias de Python necesarias
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    aiohttp \
    beautifulsoup4 \
    python-multipart \
    httpx

# Establece el usuario y grupo con UID y GID del argumento
RUN groupadd -g $GID extractor && \
    useradd -r -u $UID -g extractor extractor

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia los archivos de tu aplicación al contenedor
COPY . /app

# Crea directorios necesarios
RUN mkdir -p /home/globoscx/unews/salidas/extractor && \
    mkdir -p /app/logs

# Establece permisos adecuados
RUN chown -R extractor:extractor /home/globoscx/unews/salidas/extractor && \
    chown -R extractor:extractor /app/logs && \
    chown -R extractor:extractor /app

# Cambia al usuario no privilegiado
USER extractor

# Expone el puerto en el que correrá la aplicación
EXPOSE 8000

# Comando para ejecutar la aplicación usando Uvicorn con configuraciones optimizadas
CMD ["uvicorn", "extractor:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--timeout-keep-alive", "65"]