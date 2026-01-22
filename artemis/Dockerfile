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

EXPOSE 8000

# Run from the artemis directory to find the main module
WORKDIR /app/artemis
CMD ["uvicorn", "artemis.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
