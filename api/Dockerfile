# Backend image for Hugging Face Spaces (Docker SDK) or any container host.
# The Playwright base image ships Chromium matching playwright==1.63.0.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Spaces run the container as uid 1000; keep the database and caches writable.
ENV SCOUT_DATA_DIR=/app/data PORT=7860
RUN mkdir -p /app/data && chown -R 1000:1000 /app
USER 1000

EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
