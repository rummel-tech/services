FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
		PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
		build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

RUN useradd -u 1001 -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
	CMD python -c "import urllib.request,sys;\nurl='http://localhost:8000/health';\n\ntry: urllib.request.urlopen(url); print('ok');\nexcept Exception as e: print(e); sys.exit(1)" 

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
