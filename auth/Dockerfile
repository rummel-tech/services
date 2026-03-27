FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy common package
COPY ../common /app/common

# Copy service
COPY . /app

ENV PYTHONPATH=/app

EXPOSE 8090

CMD ["uvicorn", "auth.api.main:app", "--host", "0.0.0.0", "--port", "8090"]
