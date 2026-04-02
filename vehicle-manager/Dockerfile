FROM python:3.11-slim

WORKDIR /app

# Copy common package and its dependencies first
COPY common/ common/
RUN pip install --no-cache-dir -r common/requirements.txt

# Copy service requirements and install
COPY vehicle-manager/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY vehicle-manager/ .

# Set Python path to include common
ENV PYTHONPATH=/app:$PYTHONPATH

EXPOSE 8030

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8030/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8030"]
