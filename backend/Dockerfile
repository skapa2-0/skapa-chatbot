FROM python:3.12-slim

WORKDIR /app

# Dependances systeme minimales pour psycopg/lxml/playwright si besoin
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright + son navigateur (utile uniquement si SCRAPER_USE_PLAYWRIGHT=true)
RUN playwright install --with-deps chromium

COPY . .

EXPOSE 8000

CMD ["gunicorn", "app.api_agent:app", "--bind", "0.0.0.0:8000", "--chdir", "app/.."]
