FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
ENV ENVIRONMENT=prod

EXPOSE 8002

# Usuario sin privilegios: el servicio no necesita root en ejecucion y limitarlo
# contiene el alcance de una eventual ejecucion remota de codigo. El UID 1000 coincide
# con el usuario habitual del host para que los bind mounts de docker-compose
# (./services/<svc>/app y ./downloads) conserven permisos de escritura.
RUN groupadd -g 1000 appuser \
    && useradd -u 1000 -g appuser -m appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
