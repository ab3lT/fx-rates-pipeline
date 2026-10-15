FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so Docker can cache this layer.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN pip install --no-deps -e .

# Default: run the pipeline once against the configured source.
ENTRYPOINT ["python", "-m", "fx_etl.cli"]
