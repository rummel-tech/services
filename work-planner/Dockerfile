FROM python:3.11-slim

WORKDIR /app

COPY common/ common/
RUN pip install --no-cache-dir -r common/requirements.txt

COPY work-planner/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY work-planner/ .

ENV PYTHONPATH=/app:$PYTHONPATH

RUN useradd -u 1001 -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8040

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8040/healthz')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8040"]
