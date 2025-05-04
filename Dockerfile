FROM python:3.9-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primero para cachear
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copiar aplicación
COPY . .

# Variables de entorno
ENV PYTHONPATH=/app
ENV ENVIRONMENT=prod

# Puerto expuesto
EXPOSE 8000

# Comando de inicio
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]