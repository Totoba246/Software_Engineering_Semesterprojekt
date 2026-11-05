# One image for the API, the collector and the developer tools;
# docker-compose.yml chooses what runs via `command`.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY batterywatch ./batterywatch

RUN useradd --system --uid 10001 app
USER app

EXPOSE 8000
CMD ["uvicorn", "batterywatch.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
