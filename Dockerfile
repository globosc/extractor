# Usa una imagen base oficial de Python
FROM python:3.9-slim

# Establece la zona horaria a Chile
ENV TZ=America/Santiago

# Argumentos para UID y GID del usuario
ARG UID
ARG GID

# Actualiza el índice de paquetes, instala curl, net-tools, iputils-ping y limpia los archivos temporales
RUN apt-get update && apt-get install -y \
    curl \
    net-tools \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Instala las dependencias de Python necesarias
RUN pip install --no-cache-dir fastapi uvicorn requests beautifulsoup4

# Establece el usuario y grupo con UID y GID del argumento
RUN groupadd -g $GID extractor && \
    useradd -r -u $UID -g extractor extractor

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia los archivos de tu aplicación al contenedor
COPY . /app

# Asegura que la carpeta de salida existe
RUN mkdir -p /home/globoscx/unews/salidas/extractor

# Cambia el propietario de /home/globoscx/unews/salidas/extractor al usuario extractor
RUN chown -R extractor:extractor /home/globoscx/unews/salidas/extractor

# Expone el puerto en el que correrá la aplicación
EXPOSE 8000

# Comando para ejecutar la aplicación usando Uvicorn
CMD ["uvicorn", "extractor:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
