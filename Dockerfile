FROM python:3.11-slim

WORKDIR /app

# Install dependencies first to take advantage of Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitor.py webapp.py ./
COPY static/ ./static/

# Default: run the monitor. The web app service overrides the entrypoint with webapp.py.
# Requires /var/run/docker.sock to be mounted at runtime.
ENTRYPOINT ["python", "-u", "monitor.py"]
