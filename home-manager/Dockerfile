FROM python:3.11-slim

WORKDIR /app

# Copy common package and its dependencies first
COPY common/ common/
RUN pip install --no-cache-dir -r common/requirements.txt

# Copy service requirements and install
COPY home-manager/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY home-manager/ .

# Set Python path to include common
ENV PYTHONPATH=/app:$PYTHONPATH

EXPOSE 8020

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8020"]
