FROM python:3.11-slim

WORKDIR /app

# Copy common package (artemis modules depend on it for client and settings)
COPY common/ common/

# Copy artemis requirements and install
COPY artemis/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy artemis code
COPY artemis/ artemis/

# Set Python path to include common and artemis
ENV PYTHONPATH=/app:/app/artemis:$PYTHONPATH

RUN useradd -u 1001 -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

WORKDIR /app/artemis
CMD ["uvicorn", "artemis.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
