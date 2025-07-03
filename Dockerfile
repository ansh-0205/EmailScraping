FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/logs /app/output /app/data && \
    chmod 755 /app/logs /app/output /app/data

ENV PYTHONPATH=/app
ENV HUGGINGFACE_MODEL_NAME=Ansh0205/EmailScraping
ENV PYTHONUNBUFFERED=1

RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os; exit(0 if os.path.exists('/app/email_data.json') else 1)" || exit 1

CMD ["python", "-u", "e2.py"]