# Usa una imagen oficial de Python como imagen base
FROM python:3.8-slim

# Establece el directorio de trabajo en el contenedor
WORKDIR /app

# Agrega los archivos del directorio actual al contenedor
ADD . /app

# Instala las dependencias del proyecto
RUN pip install --no-cache-dir -r requirements.txt

# Haz ejecutable tu script
RUN chmod +x main.py

# Comando a ejecutar cuando se inicia el contenedor
CMD ["python", "./main.py"]
