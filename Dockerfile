FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so Docker can cache this layer.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN pip install --no-deps -e . \
    && useradd --create-home --uid 1000 app \
    && chown -R app /app
USER app

EXPOSE 8000

# Default: run the pipeline once against the configured source.
# docker-compose.prod.yml overrides the entrypoint for the web and scheduler services.
ENTRYPOINT ["python", "-m", "fx_etl.cli"]
