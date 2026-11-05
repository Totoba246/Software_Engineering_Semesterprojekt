# =============================================================================
#  Recipe for the BACKEND image (all our Python code)
# =============================================================================
#  A Dockerfile is a step-by-step recipe that Docker follows to build an
#  "image" (a frozen mini-computer with everything installed). Containers are
#  started from images.
#
#  ONE image is used by THREE containers (see docker-compose.yml):
#    api        -> runs the default CMD at the bottom (the REST API on port 8000)
#    collector  -> overrides CMD with "python -m batterywatch.collector"
#    publisher  -> overrides CMD with the test publisher
#
#  Built automatically by `docker compose up --build`.
# =============================================================================

# Start from an official image that already contains Python 3.12 ("slim" = small).
FROM python:3.12-slim

# PYTHONUNBUFFERED: print log lines immediately (so `docker compose logs` shows them)
# PYTHONDONTWRITEBYTECODE: don't create __pycache__ files; PIP_NO_CACHE_DIR: smaller image
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

# All following commands run in the folder /app inside the image.
WORKDIR /app

# Install the Python libraries first (listed in requirements.txt).
# Done before copying our code so Docker can reuse this slow step when only code changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy our own code (backend/batterywatch/ -> /app/batterywatch/).
COPY batterywatch ./batterywatch

# Don't run as the all-powerful "root" user inside the container (safety).
RUN useradd --system --uid 10001 app
USER app

# Documentation only: the API listens on port 8000 inside the container.
# (Which SERVER port leads here is decided in docker-compose.yml: 20801.)
EXPOSE 8000

# Default program: the web server "uvicorn" running our API (batterywatch/api/main.py).
# --host 0.0.0.0 = accept connections from other containers, not just from itself.
CMD ["uvicorn", "batterywatch.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
