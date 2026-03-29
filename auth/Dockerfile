FROM python:3.12-slim

WORKDIR /app

# Copy common package (build context must be services/ root)
COPY common/ common/
RUN pip install --no-cache-dir -r common/requirements.txt

# Copy service requirements and install
COPY auth/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY auth/ auth/

ENV PYTHONPATH=/app

EXPOSE 8090

CMD ["uvicorn", "auth.api.main:app", "--host", "0.0.0.0", "--port", "8090"]
