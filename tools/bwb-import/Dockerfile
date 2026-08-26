# Self-contained image voor de BWB-importservice (FastAPI).
FROM python:3.14-slim

WORKDIR /app

# Dependencies eerst (betere layer-caching). lxml-wheels bundelen libxml2/libxslt.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Applicatiecode en de officiële XSD's.
COPY app ./app
COPY schemas ./schemas

EXPOSE 8000

CMD ["uvicorn", "app.service:app", "--host", "0.0.0.0", "--port", "8000"]
